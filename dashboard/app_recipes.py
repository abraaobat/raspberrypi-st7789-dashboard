"""Closed, offline URL recipes. No DNS, HTTP, credentials or executable plugins."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import quote, urlencode, urlsplit, urlunsplit


APP_SOURCE_TEMPLATES = (
    {
        "id": "esphome-sensor", "name": "Sensor ESPHome (web API)",
        "description": "Sensor numérico com web_server já habilitado. Use o nome YAML exato do sensor; a unidade deve corresponder à origem. Firmwares antigos podem exigir URL manual. Autenticação do web_server não é suportada por este modelo; não a desative.",
        "fields": {"title": "Sensor ESPHome", "valueLabel": "LEITURA", "unit": "", "layout": "metric", "accent": "blue", "valuePath": "value", "secondaryPath": "state"},
        "sample": {"id": "sensor/Temperatura externa", "state": "28.1 °C", "value": 28.1},
        "endpoint": {
            "help": "GET de um sensor, sem comandos. API atual usa nomes, inclusive espaços/acentos. Nome do dispositivo é opcional para subdispositivos. Só endereço base, sem caminho de proxy.",
            "docsUrl": "https://esphome.io/web-api/",
            "parameters": [
                {"name": "entityName", "label": "Nome do sensor (YAML)", "default": "Temperatura externa", "maxLength": 80},
                {"name": "deviceName", "label": "Nome do subdispositivo (opcional)", "default": "", "maxLength": 80},
            ],
        },
    },
    {
        "id": "shelly-power", "name": "Potência Shelly (Gen2+)",
        "description": "Switch.GetStatus em modelos Gen2+ com medição. O campo apower fornece watts; nem todo Shelly possui esse campo. Não liga/desliga a saída. Autenticação Digest não é suportada por este modelo; use uma ponte autorizada, sem remover proteção.",
        "fields": {"title": "Energia Shelly", "valueLabel": "POTÊNCIA", "unit": "W", "layout": "metric", "accent": "orange", "valuePath": "apower", "secondaryPath": ""},
        "sample": {"id": 0, "source": "init", "output": True, "apower": 318, "voltage": 230},
        "endpoint": {
            "help": "GET somente de leitura: Switch.GetStatus. Canal de 0 a 63. Gen1 e modelos sem medição não são abrangidos. Não há seleção de outros métodos RPC.",
            "docsUrl": "https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Switch/",
            "parameters": [{"name": "channel", "label": "Canal do Switch", "default": "0", "maxLength": 2}],
        },
    },
    {
        "id": "prometheus-scalar", "name": "Métrica Prometheus (escalar)",
        "description": "Consulta instantânea com resultado escalar. Ajuste o seletor para uma única série e a unidade para sua métrica. scalar() com zero ou várias séries retorna NaN, não zero nem estado saudável. Vetores/histogramas exigem outro contrato.",
        "fields": {"title": "Prometheus", "valueLabel": "VALOR", "unit": "", "layout": "metric", "accent": "purple", "valuePath": "data.result.1", "secondaryPath": ""},
        "sample": {"status": "success", "data": {"resultType": "scalar", "result": [1710000000, "1"]}},
        "endpoint": {
            "help": "GET /api/v1/query, timeout solicitado de 2s. Exemplo: scalar(up{job=\"prometheus\"}). Selecione a série correta; nunca suponha ordem estável dos vetores. O helper não executa nem valida a expressão PromQL.",
            "docsUrl": "https://prometheus.io/docs/prometheus/latest/querying/api/",
            "parameters": [{"name": "expression", "label": "Expressão PromQL (resultado escalar)", "default": 'scalar(up{job="prometheus"})', "maxLength": 512}],
        },
    },
)

_PARAMETERS = {item["id"]: {field["name"] for field in item["endpoint"]["parameters"]} for item in APP_SOURCE_TEMPLATES}


def _text(value, maximum, label, optional=False, trim=True):
    if not isinstance(value, str) or len(value) > maximum or any(not char.isprintable() for char in value):
        raise ValueError(f"{label}: texto inválido ou longo demais")
    value = value.strip() if trim else value
    if (not optional or value) and not value.strip():
        raise ValueError(f"{label}: preencha o campo")
    return value


def _origin(value):
    value = _text(value, 512, "endereço base")
    if any(char.isspace() for char in value) or "\\" in value or "?" in value or "#" in value:
        raise ValueError("endereço base deve conter somente http(s), host e porta, sem caminho, query ou fragmento")
    try:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.path not in {"", "/"} or "@" in parts.netloc or "%" in parts.netloc:
            raise ValueError
        port = parts.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError
        host = parts.hostname
        if "[" in parts.netloc or "]" in parts.netloc:
            if not re.fullmatch(r"\[[^\[\]]+\](?::[0-9]+)?", parts.netloc):
                raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            host = host.encode("idna").decode("ascii").lower()
            if len(host) > 253 or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.rstrip(".").split(".")):
                raise ValueError
        else:
            checked = getattr(address, "ipv4_mapped", None) or address
            if checked.is_link_local or checked.is_multicast or checked.is_unspecified or checked.is_reserved:
                raise ValueError
            host = f"[{address}]" if address.version == 6 else str(address)
        # Do not silently accept malformed trailing separators or IPv6 syntax.
        if parts.netloc.endswith(":") or (":" in parts.hostname and not parts.netloc.startswith("[")):
            raise ValueError
        return parts.scheme, host + (f":{port}" if port is not None else "")
    except (ValueError, UnicodeError) as exc:
        raise ValueError("endereço base inválido; use http(s)://host:porta sem credenciais ou caminho. Destinos inseguros não são permitidos") from exc


def build_source_url(payload):
    """Build a fixed read endpoint, but never resolve/contact its host or save it."""
    if not isinstance(payload, dict) or set(payload) != {"templateId", "baseUrl", "parameters"}:
        raise ValueError("informe somente modelo, endereço base e parâmetros")
    recipe = payload["templateId"]
    if not isinstance(recipe, str) or recipe not in _PARAMETERS:
        raise ValueError("modelo sem montagem de URL")
    parameters = payload["parameters"]
    if not isinstance(parameters, dict) or set(parameters) != _PARAMETERS[recipe]:
        raise ValueError("parâmetros não correspondem ao modelo")
    scheme, netloc = _origin(payload["baseUrl"])
    query = ""
    if recipe == "esphome-sensor":
        names = []
        for key in ("deviceName", "entityName"):
            name = _text(parameters[key], 80, "nome YAML", optional=key == "deviceName", trim=False)
            if name in {".", ".."} or "/" in name or "\\" in name:
                raise ValueError("nome YAML não pode conter separadores de caminho")
            if name:
                names.append(quote(name, safe=""))
        path = "/sensor/" + "/".join(names)
    elif recipe == "shelly-power":
        channel = _text(parameters["channel"], 2, "canal")
        if not re.fullmatch(r"(?:0|[1-9][0-9]?)", channel) or int(channel) > 63:
            raise ValueError("canal deve ser um inteiro de 0 a 63")
        path, query = "/rpc/Switch.GetStatus", urlencode({"id": channel})
    else:
        expression = _text(parameters["expression"], 512, "expressão PromQL")
        path, query = "/api/v1/query", urlencode({"query": expression, "timeout": "2s"})
    url = urlunsplit((scheme, netloc, path, query, ""))
    if len(url) > 2048:
        raise ValueError("URL montada excede 2048 caracteres; reduza os parâmetros")
    return {"ok": True, "url": url}
