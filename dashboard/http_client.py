"""Bounded direct HTTP with DNS pinning, verified TLS and no redirects/proxies."""

from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import ssl
import time
from urllib.parse import urlsplit

MAX_JSON_BYTES = 128 * 1024
HTTP_TIMEOUT_SECONDS = 4
TAILNET = ipaddress.ip_network("100.64.0.0/10")


class SourceError(ValueError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def resolve_source(url: str, *, authenticated=False, allow_insecure_http=False):
    try:
        parsed = urlsplit(url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise SourceError("endereço da fonte inválido") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SourceError("a fonte deve usar HTTP ou HTTPS")
    if parsed.username or parsed.password:
        raise SourceError("credenciais na URL não são permitidas")
    if any(ord(char) < 33 for char in url) or "%" in parsed.hostname or "\\" in url:
        raise SourceError("endereço da fonte inválido")
    if authenticated and parsed.scheme == "http" and not allow_insecure_http:
        raise SourceError("autorize HTTP local explicitamente ou use HTTPS")
    try:
        rows = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise SourceError("não foi possível resolver o endereço da fonte") from exc
    addresses = []
    for row in rows:
        ip = ipaddress.ip_address(row[4][0])
        effective = ip.ipv4_mapped if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped else ip
        if effective.is_link_local or effective.is_multicast or effective.is_unspecified or effective.is_reserved:
            raise SourceError("endereço de rede não permitido")
        local = effective.is_private or effective.is_loopback or effective in TAILNET
        if authenticated and parsed.scheme == "http" and not local:
            raise SourceError("HTTP com credencial é permitido somente na rede local ou tailnet")
        if str(ip) not in addresses:
            addresses.append(str(ip))
    if not addresses:
        raise SourceError("não foi possível resolver o endereço da fonte")
    return parsed, port, addresses


def validate_source_url(url: str) -> None:
    resolve_source(url)


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, port, address, timeout):
        super().__init__(host, port, timeout=timeout)
        self.address = address

    def connect(self):
        self.sock = socket.create_connection((self.address, self.port), self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, port, address, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        sock = socket.create_connection((self.address, self.port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def request_json(url: str, *, method="GET", headers=None, payload=None,
                 authenticated=False, allow_insecure_http=False, timeout=HTTP_TIMEOUT_SECONDS):
    if method not in {"GET", "POST", "DELETE"}:
        raise SourceError("método HTTP não permitido")
    parsed, port, addresses = resolve_source(
        url, authenticated=authenticated, allow_insecure_http=allow_insecure_http
    )
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request_headers = {"Accept": "application/json", "User-Agent": "ST7789-Dashboard/0.4"}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    request_headers.update(headers or {})
    endpoint = parsed.path or "/"
    if parsed.query:
        endpoint += "?" + parsed.query
    deadline = time.monotonic() + timeout
    response = None
    connection = None
    try:
        # Pin the checked addresses: no second hostname lookup can send a token elsewhere.
        for address in addresses:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SourceError("tempo limite da fonte excedido")
            kind = _PinnedHTTPS if parsed.scheme == "https" else _PinnedHTTP
            connection = kind(parsed.hostname, port, address, remaining)
            try:
                connection.connect()
                break
            except ssl.SSLCertVerificationError:
                connection.close()
                raise SourceError("certificado HTTPS não confiável; configure uma CA válida") from None
            except OSError:
                connection.close()
                connection = None
        if connection is None:
            raise SourceError("fonte HTTP indisponível")
        connection.sock.settimeout(max(0.001, deadline - time.monotonic()))
        connection.request(method, endpoint, body=body, headers=request_headers)
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise SourceError("redirecionamento bloqueado; informe o endereço final", response.status)
        if response.status in {401, 403}:
            raise SourceError("credencial recusada ou sem permissão", response.status)
        if response.status == 404:
            raise SourceError("endpoint ou entidade não encontrado; confira endereço e versão", 404)
        if response.status == 429:
            raise SourceError("fonte limitou as consultas; aguarde antes de tentar novamente", 429)
        if response.status not in {200, 201, 204}:
            raise SourceError("fonte HTTP indisponível", response.status)
        if response.status == 204:
            return {}
        chunks = []
        size = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SourceError("tempo limite da fonte excedido")
            # HTTP/1.0 can detach the socket from the connection; response.fp retains it.
            raw_socket = connection.sock or getattr(getattr(response.fp, "raw", None), "_sock", None)
            if raw_socket is not None:
                raw_socket.settimeout(remaining)
            chunk = response.read1(min(8192, MAX_JSON_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_JSON_BYTES:
                raise SourceError("resposta JSON excede 128 KiB")
        result = json.loads(b"".join(chunks).decode("utf-8"))
        if not isinstance(result, (dict, list)):
            raise SourceError("a raiz da resposta deve ser objeto ou lista JSON")
        return result
    except (UnicodeError, json.JSONDecodeError):
        raise SourceError("a fonte não retornou JSON válido") from None
    except (OSError, http.client.HTTPException):
        raise SourceError("fonte HTTP indisponível ou tempo limite excedido") from None
    finally:
        if response is not None:
            response.close()
        if connection is not None:
            connection.close()
