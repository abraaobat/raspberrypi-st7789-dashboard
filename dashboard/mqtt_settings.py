"""Closed, secret-free settings for a read-only MQTT snapshot source."""

from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

PATH = re.compile(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$")


class MQTTError(ValueError):
    """Safe error; never include a broker's response or credentials."""


def clean_text(value, name, maximum, *, required=False):
    if not isinstance(value, str) or len(value) > maximum:
        raise MQTTError(f"{name}: informe texto de até {maximum} caracteres")
    if any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF
           or ord(c) & 0xFFFF in {0xFFFE, 0xFFFF} or 0xFDD0 <= ord(c) <= 0xFDEF for c in value):
        raise MQTTError(f"{name}: caracteres inválidos")
    if required and not value.strip():
        raise MQTTError(f"{name} é obrigatório")
    return value


def broker_url(value, *, required=False):
    value = clean_text(value, "broker MQTT", 512).strip()
    if not value and not required:
        return ""
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"mqtt", "mqtts"} or not parsed.hostname:
            raise ValueError()
        if parsed.username is not None or parsed.password is not None or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError()
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        if any(c.isspace() for c in value) or any(c in host for c in "%\\"):
            raise ValueError()
        port = parsed.port or (8883 if parsed.scheme == "mqtts" else 1883)
        if not 1 <= port <= 65535 or parsed.port == 0:
            raise ValueError()
        host = f"[{host}]" if ":" in host else host
        return f"{parsed.scheme}://{host}:{port}"
    except (ValueError, UnicodeError) as exc:
        raise MQTTError("use mqtts://servidor:8883 ou mqtt://IP-local:1883, sem senha na URL") from exc


def mqtt_settings(payload):
    if not isinstance(payload, dict) or set(payload) - {"brokerUrl", "allowInsecureMqtt", "sensors"}:
        raise MQTTError("ajustes MQTT inválidos")
    consent = payload.get("allowInsecureMqtt", False)
    if not isinstance(consent, bool):
        raise MQTTError("a autorização MQTT local deve ser verdadeira ou falsa")
    sensors = payload.get("sensors", [])
    if not isinstance(sensors, list) or len(sensors) > 4:
        raise MQTTError("escolha até quatro sensores MQTT")
    result, topics = [], set()
    for sensor in sensors:
        if not isinstance(sensor, dict) or set(sensor) - {"label", "topic", "format", "valuePath", "unit"}:
            raise MQTTError("sensor MQTT inválido")
        topic = clean_text(sensor.get("topic", ""), "tópico", 200, required=True)
        if any(c in topic for c in "+#") or topic.startswith("$share/") or topic in topics:
            raise MQTTError("use tópicos exatos e diferentes, sem +, # ou assinatura compartilhada")
        topics.add(topic)
        fmt = sensor.get("format", "text")
        path = clean_text(sensor.get("valuePath", ""), "caminho JSON", 120)
        if fmt not in {"text", "json"} or (fmt == "json" and not PATH.fullmatch(path)) or (fmt == "text" and path):
            raise MQTTError("escolha texto simples ou JSON com caminho válido")
        result.append({"label": clean_text(sensor.get("label", ""), "nome", 18, required=True).strip(),
                       "topic": topic, "format": fmt, "valuePath": path,
                       "unit": clean_text(sensor.get("unit", ""), "unidade", 10)})
    return {"brokerUrl": broker_url(payload.get("brokerUrl", "")), "allowInsecureMqtt": consent, "sensors": result}


def encode_credentials(username, password):
    username = clean_text(username, "usuário MQTT", 128, required=True)
    password = clean_text(password, "senha MQTT", 1024)
    return json.dumps({"username": username, "password": password}, ensure_ascii=False)


def decode_credentials(secret):
    try:
        payload = json.loads(secret)
        if not isinstance(payload, dict) or set(payload) != {"username", "password"}:
            raise ValueError()
        encode_credentials(payload["username"], payload["password"])
        return payload
    except (ValueError, TypeError, KeyError) as exc:
        raise MQTTError("credencial MQTT inválida; guarde-a novamente no painel") from exc
