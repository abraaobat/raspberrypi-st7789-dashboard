"""Validated, atomic configuration storage for the dashboard."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

from .catalog import PAGE_BY_ID, PAGE_CATALOG

APP_DIR_NAME = "raspberrypi-st7789-dashboard"


class ConfigError(ValueError):
    """Raised when a configuration payload is not valid."""


def state_dir(override: str | Path | None = None) -> Path:
    if override is not None:
        return Path(override).expanduser()
    configured = os.environ.get("ST7789_DASHBOARD_STATE_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".config" / APP_DIR_NAME


def config_path(override: str | Path | None = None) -> Path:
    return state_dir(override) / "config.json"


def default_config() -> dict:
    return {
        "schemaVersion": 1,
        "theme": "dark",
        "temperatureUnit": "celsius",
        "carousel": {
            "enabled": False,
            "intervalSeconds": 8,
            "resumeAfterSeconds": 30,
        },
        "thresholds": {
            "temperatureWarning": 60,
            "temperatureCritical": 70,
        },
        "pages": [
            {
                "id": page["id"],
                "enabled": page["defaultEnabled"],
                "refreshSeconds": page["defaultRefreshSeconds"],
            }
            for page in PAGE_CATALOG
        ],
    }


def _bounded_int(value, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ConfigError(f"{name} deve ser um número inteiro")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} deve ser um número inteiro") from exc
    if not minimum <= parsed <= maximum:
        raise ConfigError(f"{name} deve estar entre {minimum} e {maximum}")
    return parsed


def normalize_config(payload: dict | None) -> dict:
    if payload is None:
        return default_config()
    if not isinstance(payload, dict):
        raise ConfigError("configuração deve ser um objeto JSON")

    result = default_config()

    if payload.get("schemaVersion", 1) != 1:
        raise ConfigError("schemaVersion não suportado")

    theme = payload.get("theme", result["theme"])
    if theme not in {"dark"}:
        raise ConfigError("tema não suportado")
    result["theme"] = theme

    temperature_unit = payload.get("temperatureUnit", result["temperatureUnit"])
    if temperature_unit not in {"celsius", "fahrenheit"}:
        raise ConfigError("temperatureUnit deve ser celsius ou fahrenheit")
    result["temperatureUnit"] = temperature_unit

    carousel = payload.get("carousel", {})
    if not isinstance(carousel, dict):
        raise ConfigError("carousel deve ser um objeto")
    result["carousel"] = {
        "enabled": bool(carousel.get("enabled", result["carousel"]["enabled"])),
        "intervalSeconds": _bounded_int(
            carousel.get("intervalSeconds", result["carousel"]["intervalSeconds"]),
            "carousel.intervalSeconds",
            2,
            300,
        ),
        "resumeAfterSeconds": _bounded_int(
            carousel.get("resumeAfterSeconds", result["carousel"]["resumeAfterSeconds"]),
            "carousel.resumeAfterSeconds",
            0,
            3600,
        ),
    }

    thresholds = payload.get("thresholds", {})
    if not isinstance(thresholds, dict):
        raise ConfigError("thresholds deve ser um objeto")
    warning = _bounded_int(
        thresholds.get("temperatureWarning", result["thresholds"]["temperatureWarning"]),
        "thresholds.temperatureWarning",
        20,
        100,
    )
    critical = _bounded_int(
        thresholds.get("temperatureCritical", result["thresholds"]["temperatureCritical"]),
        "thresholds.temperatureCritical",
        20,
        120,
    )
    if critical <= warning:
        raise ConfigError("temperatura crítica deve ser maior que a temperatura de alerta")
    result["thresholds"] = {
        "temperatureWarning": warning,
        "temperatureCritical": critical,
    }

    requested_pages = payload.get("pages", result["pages"])
    if not isinstance(requested_pages, list):
        raise ConfigError("pages deve ser uma lista")

    normalized_pages = []
    seen = set()
    for item in requested_pages:
        if not isinstance(item, dict):
            raise ConfigError("cada página deve ser um objeto")
        page_id = item.get("id")
        if page_id not in PAGE_BY_ID:
            raise ConfigError(f"página desconhecida: {page_id!r}")
        if page_id in seen:
            raise ConfigError(f"página duplicada: {page_id}")
        seen.add(page_id)
        metadata = PAGE_BY_ID[page_id]
        normalized_pages.append(
            {
                "id": page_id,
                "enabled": bool(item.get("enabled", metadata["defaultEnabled"])),
                "refreshSeconds": _bounded_int(
                    item.get("refreshSeconds", metadata["defaultRefreshSeconds"]),
                    f"pages.{page_id}.refreshSeconds",
                    metadata["minRefreshSeconds"],
                    3600,
                ),
            }
        )

    for metadata in PAGE_CATALOG:
        if metadata["id"] not in seen:
            normalized_pages.append(
                {
                    "id": metadata["id"],
                    "enabled": False,
                    "refreshSeconds": metadata["defaultRefreshSeconds"],
                }
            )

    if not any(page["enabled"] for page in normalized_pages):
        raise ConfigError("ao menos uma página deve permanecer ativa")

    result["pages"] = normalized_pages
    return result


def load_config(override: str | Path | None = None) -> dict:
    path = config_path(override)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return normalize_config(payload)
    except FileNotFoundError:
        return default_config()
    except (json.JSONDecodeError, ConfigError, OSError):
        return default_config()


def save_config(payload: dict, override: str | Path | None = None) -> dict:
    normalized = normalize_config(payload)
    directory = state_dir(override)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        directory.chmod(0o700)
    except OSError:
        pass

    destination = config_path(override)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    os.replace(temporary, destination)
    return copy.deepcopy(normalized)


def enabled_pages(config: dict) -> list[dict]:
    return [page for page in config["pages"] if page.get("enabled")]


class ConfigStore:
    """Small mtime-aware cache used by the high-frequency display loop."""

    def __init__(self, override: str | Path | None = None):
        self.override = override
        self.path = config_path(override)
        self._mtime_ns = None
        self._config = default_config()

    def load(self, force: bool = False) -> dict:
        try:
            mtime_ns = self.path.stat().st_mtime_ns
        except OSError:
            mtime_ns = None
        if force or mtime_ns != self._mtime_ns:
            self._config = load_config(self.override)
            self._mtime_ns = mtime_ns
        return copy.deepcopy(self._config)
