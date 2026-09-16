"""Closed, nonsecret settings contract for guided integrations."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

INTEGRATION_IDS = ("pihole", "homeassistant")
ENTITY_PATTERN = re.compile(r"[a-z0-9_]+\.[a-z0-9_]+$")
PATH_PATTERN = re.compile(r"(?:/[A-Za-z0-9_-]+)*$")


def base_url(value, *, required=False) -> str:
    if not isinstance(value, str):
        raise ValueError("o endereço da integração deve ser texto")
    value = value.strip()
    if not value and not required:
        return ""
    if len(value) > 512 or any(ord(char) < 33 for char in value):
        raise ValueError("endereço da integração inválido")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("endereço ou porta da integração inválidos") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("use o endereço HTTP ou HTTPS do serviço")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("não inclua credenciais, parâmetros ou fragmentos no endereço")
    host = parsed.hostname.lower().rstrip(".")
    if "%" in host or "\\" in host:
        raise ValueError("nome de servidor inválido")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("nome de servidor inválido") from exc
    if ":" in host:
        host = f"[{host}]"
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("porta da integração inválida")
    default_port = 443 if parsed.scheme == "https" else 80
    netloc = host if port in {None, default_port} else f"{host}:{port}"
    prefix = parsed.path.rstrip("/")
    if not PATH_PATTERN.fullmatch(prefix) or prefix.endswith(("/api", "/admin")):
        raise ValueError("use o endereço base do serviço, sem /api ou /admin")
    return urlunsplit((parsed.scheme, netloc, prefix, "", ""))


def integration_settings(connector: str, payload) -> dict:
    if connector not in INTEGRATION_IDS:
        raise ValueError("integração não suportada")
    if not isinstance(payload, dict):
        raise ValueError("os ajustes da integração devem ser um objeto")
    allowed = {"baseUrl", "allowInsecureHttp"}
    if connector == "homeassistant":
        allowed.add("entities")
    if set(payload) - allowed:
        raise ValueError("ajuste não permitido; credenciais devem usar o cofre separado")
    insecure = payload.get("allowInsecureHttp", False)
    if not isinstance(insecure, bool):
        raise ValueError("a autorização de HTTP deve ser verdadeiro ou falso")
    result = {"baseUrl": base_url(payload.get("baseUrl", "")), "allowInsecureHttp": insecure}
    if connector == "homeassistant":
        entities = payload.get("entities", [])
        if not isinstance(entities, list) or len(entities) > 4:
            raise ValueError("escolha no máximo quatro entidades do Home Assistant")
        normalized = []
        for entity in entities:
            if not isinstance(entity, str) or len(entity) > 120 or not ENTITY_PATTERN.fullmatch(entity):
                raise ValueError("entidade inválida; use um identificador como sensor.energia")
            if entity in normalized:
                raise ValueError("entidade duplicada")
            normalized.append(entity)
        result["entities"] = normalized
    return result
