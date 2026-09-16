"""Read-only guided connectors; authentication is never browser-visible."""

from __future__ import annotations

import math

from .credentials import validate_secret
from .http_client import SourceError, request_json
from .integration_settings import base_url, integration_settings


def _number(value, *, maximum=10**15):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not 0 <= value <= maximum or not math.isfinite(value):
        return None
    return value


def _safe_text(value, secret: str, maximum=80):
    if not isinstance(value, (str, int, float, bool)):
        return "-"
    text = str(value).replace(secret, "[oculto]")
    return "".join(char for char in text if ord(char) >= 32)[:maximum]


def fetch_pihole(settings: dict, password: str) -> dict:
    address = base_url(settings["baseUrl"], required=True)
    options = {"authenticated": True, "allow_insecure_http": settings["allowInsecureHttp"]}
    auth = request_json(address + "/api/auth", method="POST", payload={"password": password}, **options)
    session = auth.get("session") if isinstance(auth, dict) else None
    if not isinstance(session, dict) or session.get("valid") is not True:
        raise SourceError("Pi-hole 6 recusou a sessão; use uma senha de aplicativo")
    sid = session.get("sid")
    if not isinstance(sid, str) or not 1 <= len(sid) <= 256 or not sid.isascii() or any(ord(char) < 33 for char in sid):
        raise SourceError("sessão Pi-hole 6 inválida; confira a versão da API")
    headers = {"X-FTL-SID": sid}
    try:
        summary = request_json(address + "/api/stats/summary", headers=headers, **options)
        queries = summary.get("queries") if isinstance(summary, dict) else None
        if not isinstance(queries, dict):
            raise SourceError("resumo Pi-hole inválido; este conector requer Pi-hole 6")
        total = _number(queries.get("total"))
        blocked = _number(queries.get("blocked"))
        if total is None or blocked is None:
            raise SourceError("estatísticas Pi-hole indisponíveis")
        percent = _number(queries.get("percent_blocked"), maximum=100)
        if percent is None:
            percent = min(100, blocked * 100 / total) if total else 0
        clients = summary.get("clients") or {}
        gravity = summary.get("gravity") or {}
        if not isinstance(clients, dict) or not isinstance(gravity, dict):
            raise SourceError("resumo Pi-hole inválido")
        return {
            "configured": True,
            "totalQueries": total,
            "blockedQueries": blocked,
            "blockedPercent": percent,
            "activeClients": _number(clients.get("active")),
            "blockedDomains": _number(gravity.get("domains_being_blocked")),
        }
    finally:
        # Release only the short-lived session this connector created, not other logins.
        try:
            request_json(address + "/api/auth", method="DELETE", headers=headers, **options)
        except ValueError:
            pass  # A failed logout must not discard successfully collected statistics.


def fetch_homeassistant(settings: dict, token: str) -> dict:
    address = base_url(settings["baseUrl"], required=True)
    if not settings["entities"]:
        raise SourceError("escolha pelo menos uma entidade do Home Assistant")
    rows = []
    for entity in settings["entities"]:
        try:
            payload = request_json(
                address + "/api/states/" + entity,
                headers={"Authorization": "Bearer " + token},
                authenticated=True,
                allow_insecure_http=settings["allowInsecureHttp"],
            )
        except SourceError as exc:
            if exc.status != 404:
                raise
            rows.append({"entityId": entity, "label": entity, "state": "não encontrada", "unit": "", "available": False})
            continue
        if not isinstance(payload, dict) or payload.get("entity_id") != entity or not isinstance(payload.get("state"), str):
            raise SourceError("estado Home Assistant inválido")
        attributes = payload.get("attributes") or {}
        if not isinstance(attributes, dict):
            raise SourceError("atributos Home Assistant inválidos")
        state = _safe_text(payload["state"], token, 48)
        rows.append({
            "entityId": entity,
            "label": _safe_text(attributes.get("friendly_name") or entity, token, 48),
            "state": state,
            "unit": _safe_text(attributes.get("unit_of_measurement") or "", token, 10),
            "available": payload["state"] not in {"unavailable", "unknown"},
        })
    return {"configured": True, "entities": rows}


def fetch_integration(connector: str, settings: dict, secret: str) -> dict:
    settings = integration_settings(connector, settings)
    secret = validate_secret(connector, secret)
    if connector == "pihole":
        return fetch_pihole(settings, secret)
    return fetch_homeassistant(settings, secret)
