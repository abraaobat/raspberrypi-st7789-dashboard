"""Bounded MQTT 3.1.1 snapshot subscriber, not a general-purpose MQTT client.

Clean sessions, exact topics, requested QoS 0, no will, no outgoing PUBLISH.
Short subscriptions favour retained sensor values, not event delivery guarantees.
"""

from __future__ import annotations

import json
import math
import secrets
import socket
import ssl
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .http_client import SourceError, resolve_source
from .mqtt_settings import MQTTError, clean_text, decode_credentials, mqtt_settings

TIMEOUT_SECONDS = 4
MAX_PACKET_BYTES = 8192
MAX_TOTAL_BYTES = 32 * 1024
MAX_PACKETS = 32


def _string(value):
    encoded = value.encode("utf-8")
    return len(encoded).to_bytes(2, "big") + encoded


def _packet(header, body):
    length, encoded = len(body), bytearray([header])
    while True:
        digit = length % 128
        length //= 128
        encoded.append(digit | (128 if length else 0))
        if not length:
            return bytes(encoded) + body


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError()
    return remaining


def _read(sock, size, deadline):
    data = bytearray()
    while len(data) < size:
        sock.settimeout(_remaining(deadline))
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise MQTTError("o broker encerrou a conexão MQTT")
        data.extend(chunk)
    return bytes(data)


def _receive(sock, deadline):
    header = _read(sock, 1, deadline)[0]
    length, multiplier = 0, 1
    try:
        for index in range(4):
            digit = _read(sock, 1, deadline)[0]
            length += (digit & 127) * multiplier
            if length > MAX_PACKET_BYTES:
                raise MQTTError("mensagem MQTT excede o limite de 8 KiB")
            if not digit & 128:
                if index and digit == 0:
                    raise MQTTError("pacote MQTT inválido")
                return header, _read(sock, length, deadline)
            multiplier *= 128
    except TimeoutError as exc:
        raise MQTTError("tempo limite excedido durante um pacote MQTT incompleto") from exc
    raise MQTTError("pacote MQTT inválido")


def _send(sock, header, body, deadline):
    sock.settimeout(_remaining(deadline))
    sock.sendall(_packet(header, body))


def sensor_value(payload, sensor):
    try:
        text = payload.decode("utf-8")
        if sensor["format"] == "json":
            value = json.loads(text, parse_constant=lambda _: None)
            for part in sensor["valuePath"].split("."):
                value = value[int(part)] if isinstance(value, list) and part.isdecimal() else value[part]
        else:
            value = text.strip()
        if value is None:
            return None
        if not isinstance(value, (str, int, float, bool)) or isinstance(value, float) and not math.isfinite(value):
            raise ValueError()
        if isinstance(value, bool):
            return "true" if value else "false"
        value = str(value)
        clean_text(value, "valor MQTT", MAX_PACKET_BYTES)
        return value[:80] if value else None
    except (UnicodeError, ValueError, TypeError, KeyError, IndexError, RecursionError) as exc:
        raise MQTTError("payload inválido ou caminho JSON não encontrado") from exc


def fetch_mqtt(settings, secret=None, *, timeout=TIMEOUT_SECONDS):
    settings = mqtt_settings(settings)
    if not settings["brokerUrl"] or not settings["sensors"]:
        raise MQTTError("configure o broker e pelo menos um sensor MQTT no painel")
    broker = urlsplit(settings["brokerUrl"])
    # Reuse the checked/pinned network policy. Plain MQTT is local-only, even anonymously.
    plain = broker.scheme == "mqtt"
    try:
        _, port, addresses = resolve_source(
            f"{'http' if plain else 'https'}://{broker.netloc}", authenticated=plain,
            allow_insecure_http=settings["allowInsecureMqtt"],
        )
    except SourceError as exc:
        raise MQTTError("broker não permitido; use TLS válido ou autorize MQTT sem TLS somente na rede local") from exc
    credentials = decode_credentials(secret) if secret is not None else None
    # The deadline covers connection, TLS, headers and payloads after DNS resolution.
    deadline, sock = time.monotonic() + timeout, None
    try:
        for address in addresses:
            try:
                sock = socket.create_connection((address, port), _remaining(deadline))
                break
            except OSError:
                sock = None
        if sock is None:
            raise MQTTError("broker MQTT indisponível")
        if not plain:
            sock.settimeout(_remaining(deadline))
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=broker.hostname)
        flags = 2 | (192 if credentials else 0)
        body = _string("MQTT") + bytes([4, flags]) + b"\x00\x0f" + _string("st7789-" + secrets.token_hex(8))
        if credentials:
            body += _string(credentials["username"]) + _string(credentials["password"])
        _send(sock, 0x10, body, deadline)
        header, response = _receive(sock, deadline)
        if header != 0x20 or len(response) != 2 or response[0] != 0 or response[1] != 0:
            raise MQTTError("conexão MQTT recusada ou resposta inválida; confira usuário e ACL do broker")
        topics = {sensor["topic"]: sensor for sensor in settings["sensors"]}
        _send(sock, 0x82, b"\x00\x01" + b"".join(_string(topic) + b"\x00" for topic in topics), deadline)
        acknowledged, values, denied = False, {}, set()
        total = 0
        for _ in range(MAX_PACKETS):
            try:
                header, message = _receive(sock, deadline)
            except TimeoutError:
                if acknowledged:
                    break  # No retained/current value is not OFF, zero, or healthy.
                raise
            total += len(message)
            if total > MAX_TOTAL_BYTES:
                raise MQTTError("consulta MQTT excede o limite de 32 KiB")
            if header == 0x90:
                if acknowledged or len(message) != 2 + len(topics) or message[:2] != b"\x00\x01" or any(code not in {0, 128} for code in message[2:]):
                    raise MQTTError("confirmação de assinatura MQTT inválida")
                acknowledged = True
                denied = {topic for topic, code in zip(topics, message[2:]) if code == 128}
            elif header in {0x30, 0x31}:  # QoS 0 only; retained flag is preserved, never interpreted as fresh publication.
                if len(message) < 2:
                    raise MQTTError("mensagem MQTT inválida")
                size = int.from_bytes(message[:2], "big")
                if not size or 2 + size > len(message):
                    raise MQTTError("mensagem MQTT inválida")
                topic = message[2:2 + size].decode("utf-8")
                if topic not in topics:
                    raise MQTTError("o broker enviou um tópico não solicitado")
                try:
                    value, error = sensor_value(message[2 + size:], topics[topic]), None
                except MQTTError as exc:
                    value, error = None, str(exc)
                values[topic] = {"value": value, "error": error, "retained": bool(header & 1)}
            else:
                raise MQTTError("pacote MQTT não suportado; esta fonte solicita apenas QoS 0")
            if acknowledged and len(set(values) | denied) == len(topics):
                break
        else:
            raise MQTTError("consulta MQTT excede o limite de 32 pacotes")
        if not acknowledged:
            raise MQTTError("assinatura MQTT não confirmada")
        rows = [{**sensor, **values.get(topic, {"value": None, "retained": False}),
                 "error": "assinatura recusada pelo broker" if topic in denied else values.get(topic, {}).get("error")}
                for topic, sensor in topics.items()]
        _send(sock, 0xE0, b"", deadline) if deadline > time.monotonic() else None
        return {"available": True, "sensors": rows, "received": sum(row["value"] is not None for row in rows),
                "receivedAt": datetime.now(timezone.utc).isoformat(), "missingTopics": [row["topic"] for row in rows if row["value"] is None]}
    except ssl.SSLCertVerificationError as exc:
        raise MQTTError("certificado MQTT TLS não confiável; configure uma CA válida") from exc
    except (OSError, TimeoutError, UnicodeError) as exc:
        raise MQTTError("broker MQTT indisponível ou tempo limite excedido") from exc
    finally:
        if sock is not None:
            sock.close()
