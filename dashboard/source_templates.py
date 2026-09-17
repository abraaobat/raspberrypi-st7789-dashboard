"""HTTP/JSON starting points; no destinations, credentials or executable code."""

from __future__ import annotations

import copy
import json

from .config import JSON_PATH_PATTERN
from .providers import extract_custom_values
from .app_recipes import APP_SOURCE_TEMPLATES


SOURCE_TEMPLATES = (
    {
        "id": "metric", "name": "Métrica simples",
        "description": "Um número e um detalhe: adapte os caminhos à resposta do seu app.",
        "fields": {"title": "Minha métrica", "valueLabel": "VALOR", "unit": "", "layout": "metric", "accent": "cyan", "valuePath": "value", "secondaryPath": "detail"},
        "sample": {"value": 42, "detail": "Atualizado agora"},
    },
    {
        "id": "service", "name": "Status de serviço",
        "description": "Mostra a saúde de um serviço sem executar ações. Estados não reconhecidos ficam neutros, não são tratados como desligados.",
        "fields": {"title": "Meu serviço", "valueLabel": "ESTADO", "unit": "", "layout": "status", "accent": "green", "valuePath": "health.status", "secondaryPath": "health.message"},
        "sample": {"health": {"status": "OK", "message": "Todos os componentes disponíveis"}},
    },
    {
        "id": "temperature", "name": "Sensor de temperatura",
        "description": "Temperatura e descrição do ambiente; o app de origem deve fornecer a unidade indicada.",
        "fields": {"title": "Temperatura", "valueLabel": "AMBIENTE", "unit": "°C", "layout": "metric", "accent": "blue", "valuePath": "sensor.temperature", "secondaryPath": "sensor.detail"},
        "sample": {"sensor": {"temperature": 28.1, "detail": "Sala · umidade 65%"}},
    },
    {
        "id": "energy", "name": "Consumo de energia",
        "description": "Potência instantânea em watts e resumo já formatado pelo medidor.",
        "fields": {"title": "Energia", "valueLabel": "POTÊNCIA", "unit": "W", "layout": "metric", "accent": "orange", "valuePath": "meter.power", "secondaryPath": "meter.detail"},
        "sample": {"meter": {"power": 318, "detail": "Hoje: 2.4 kWh"}},
    },
    {
        "id": "node-red", "name": "Node-RED via HTTP",
        "description": "Consome um endpoint GET/JSON criado no Node-RED. Não se conecta ao broker MQTT nem à API administrativa.",
        "fields": {"title": "Node-RED", "valueLabel": "AUTOMAÇÃO", "unit": "", "layout": "metric", "accent": "purple", "valuePath": "dashboard.value", "secondaryPath": "dashboard.detail"},
        "sample": {"dashboard": {"value": 23, "detail": "Sensor da bancada"}},
    },
    {
        "id": "list-item", "name": "Item de uma lista",
        "description": "Exemplo de caminho com índice de lista. Confira se a posição é estável na sua API.",
        "fields": {"title": "Meu dispositivo", "valueLabel": "ESTADO", "unit": "", "layout": "status", "accent": "cyan", "valuePath": "items.0.status", "secondaryPath": "items.0.name"},
        "sample": {"items": [{"name": "Bancada", "status": "ONLINE"}]},
    },
) + APP_SOURCE_TEMPLATES


def public_source_templates() -> list[dict]:
    """Never let a caller mutate the process-wide examples."""
    return copy.deepcopy(list(SOURCE_TEMPLATES))


def inspect_source_sample(payload) -> dict:
    """Extract only selected scalar values from supplied JSON, without network or writes."""
    if not isinstance(payload, dict) or set(payload) != {"sample", "valuePath", "secondaryPath"}:
        raise ValueError("informe somente exemplo JSON e os dois caminhos")
    if not isinstance(payload["sample"], (dict, list)):
        raise ValueError("o exemplo JSON deve ser um objeto ou uma lista")
    try:
        sample_bytes = json.dumps(payload["sample"], ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise ValueError("exemplo JSON inválido") from exc
    if len(sample_bytes) > 32 * 1024:
        raise ValueError("o exemplo deve ter no máximo 32 KiB")
    paths = {}
    for name in ("valuePath", "secondaryPath"):
        value = payload[name]
        if not isinstance(value, str) or len(value) > 120:
            raise ValueError("caminhos JSON devem ser textos de até 120 caracteres")
        value = value.strip()
        if (name == "valuePath" and not value) or (value and not JSON_PATH_PATTERN.fullmatch(value)):
            raise ValueError("caminho JSON inválido")
        paths[name] = value
    return extract_custom_values(payload["sample"], paths["valuePath"], paths["secondaryPath"])
