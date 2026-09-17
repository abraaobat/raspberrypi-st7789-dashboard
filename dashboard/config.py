"""Validated, atomic configuration storage for the dashboard."""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from .catalog import PAGE_CATALOG, catalog_by_id
from .display_profiles import DEFAULT_PROFILE_ID, PROFILE_BY_ID
from .integration_settings import INTEGRATION_IDS, integration_settings
from .desk_settings import DeskError, clock_settings, pomodoro_settings
from .docker_monitor import DockerError, docker_settings

APP_DIR_NAME = "raspberrypi-st7789-dashboard"
CUSTOM_ID_PATTERN = re.compile(r"custom:[a-z0-9][a-z0-9-]{0,31}$")
SERVICE_PATTERN = re.compile(r"[A-Za-z0-9@_.-]{1,80}(?:\.service)?$")
JSON_PATH_PATTERN = re.compile(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+|\.\d+)*$")
ACCENTS = {"blue", "cyan", "green", "orange", "purple", "red"}


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
        "displayProfile": DEFAULT_PROFILE_ID,
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
        "weather": {
            "locationName": "",
            "latitude": None,
            "longitude": None,
            "refreshMinutes": 15,
        },
        "sysops": {
            "services": [],
        },
        "docker": {"names": []},
        "customPages": [],
        "clock": clock_settings({}),
        "pomodoro": pomodoro_settings({}),
        "integrations": {connector: integration_settings(connector, {}) for connector in INTEGRATION_IDS},
        "pages": [
            {
                "id": page["id"],
                "enabled": page["defaultEnabled"],
                "refreshSeconds": page["defaultRefreshSeconds"],
            }
            for page in PAGE_CATALOG
        ],
    }


def _text(value, name: str, maximum: int, *, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ConfigError(f"{name} deve ser texto")
    value = value.strip()
    if required and not value:
        raise ConfigError(f"{name} é obrigatório")
    if len(value) > maximum:
        raise ConfigError(f"{name} deve ter no máximo {maximum} caracteres")
    return value


def _optional_float(value, name: str, minimum: float, maximum: float) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ConfigError(f"{name} deve ser um número")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} deve ser um número") from exc
    if not minimum <= parsed <= maximum:
        raise ConfigError(f"{name} deve estar entre {minimum} e {maximum}")
    return parsed


def _custom_page(item: dict, index: int) -> dict:
    if not isinstance(item, dict):
        raise ConfigError("cada página personalizada deve ser um objeto")
    page_id = _text(item.get("id"), f"customPages.{index}.id", 39, required=True)
    if not CUSTOM_ID_PATTERN.fullmatch(page_id):
        raise ConfigError(f"id de página personalizada inválido: {page_id!r}")

    source = item.get("source")
    if not isinstance(source, dict) or source.get("type") != "http-json":
        raise ConfigError(f"customPages.{index}.source deve usar http-json")
    url = _text(source.get("url"), f"customPages.{index}.source.url", 2048, required=True)
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigError(f"customPages.{index}.source.url deve usar HTTP ou HTTPS")
    if parsed.username or parsed.password:
        raise ConfigError("credenciais não devem ser incluídas na URL")

    value_path = _text(
        source.get("valuePath"),
        f"customPages.{index}.source.valuePath",
        120,
        required=True,
    )
    secondary_path = _text(
        source.get("secondaryPath"),
        f"customPages.{index}.source.secondaryPath",
        120,
    )
    if not JSON_PATH_PATTERN.fullmatch(value_path):
        raise ConfigError(f"caminho JSON principal inválido: {value_path!r}")
    if secondary_path and not JSON_PATH_PATTERN.fullmatch(secondary_path):
        raise ConfigError(f"caminho JSON secundário inválido: {secondary_path!r}")

    layout = item.get("layout", "metric")
    if layout not in {"metric", "status"}:
        raise ConfigError(f"customPages.{index}.layout inválido")
    accent = item.get("accent", "cyan")
    if accent not in ACCENTS:
        raise ConfigError(f"customPages.{index}.accent inválido")

    return {
        "id": page_id,
        "title": _text(item.get("title"), f"customPages.{index}.title", 22, required=True),
        "description": _text(item.get("description"), f"customPages.{index}.description", 90),
        "layout": layout,
        "valueLabel": _text(item.get("valueLabel"), f"customPages.{index}.valueLabel", 18),
        "unit": _text(item.get("unit"), f"customPages.{index}.unit", 10),
        "accent": accent,
        "source": {
            "type": "http-json",
            "url": url,
            "valuePath": value_path,
            "secondaryPath": secondary_path,
        },
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

    display_profile = payload.get("displayProfile", result["displayProfile"])
    selected_profile = PROFILE_BY_ID.get(display_profile)
    if selected_profile is None or not selected_profile.available:
        raise ConfigError("displayProfile não suportado por esta instalação")
    result["displayProfile"] = display_profile

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

    weather = payload.get("weather", {})
    if not isinstance(weather, dict):
        raise ConfigError("weather deve ser um objeto")
    latitude = _optional_float(weather.get("latitude"), "weather.latitude", -90, 90)
    longitude = _optional_float(weather.get("longitude"), "weather.longitude", -180, 180)
    if (latitude is None) != (longitude is None):
        raise ConfigError("latitude e longitude do clima devem ser informadas juntas")
    result["weather"] = {
        "locationName": _text(weather.get("locationName"), "weather.locationName", 32),
        "latitude": latitude,
        "longitude": longitude,
        "refreshMinutes": _bounded_int(
            weather.get("refreshMinutes", result["weather"]["refreshMinutes"]),
            "weather.refreshMinutes",
            10,
            180,
        ),
    }

    sysops = payload.get("sysops", {})
    if not isinstance(sysops, dict):
        raise ConfigError("sysops deve ser um objeto")
    services = sysops.get("services", [])
    if not isinstance(services, list) or len(services) > 4:
        raise ConfigError("sysops.services deve ter no máximo quatro serviços")
    normalized_services = []
    for service in services:
        service = _text(service, "sysops.services", 80, required=True)
        if not SERVICE_PATTERN.fullmatch(service):
            raise ConfigError(f"nome de serviço inválido: {service!r}")
        if service not in normalized_services:
            normalized_services.append(service)
    result["sysops"] = {"services": normalized_services}

    try:
        result["docker"] = docker_settings(payload.get("docker", {}))
    except DockerError as exc:
        raise ConfigError(str(exc)) from exc

    try:
        result["clock"] = clock_settings(payload.get("clock", {}))
        result["pomodoro"] = pomodoro_settings(payload.get("pomodoro", {}))
    except DeskError as exc:
        raise ConfigError(str(exc)) from exc

    integrations = payload.get("integrations", {})
    if not isinstance(integrations, dict) or set(integrations) - set(INTEGRATION_IDS):
        raise ConfigError("integração não suportada")
    try:
        result["integrations"] = {
            connector: integration_settings(connector, integrations.get(connector, {}))
            for connector in INTEGRATION_IDS
        }
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc

    custom_pages = payload.get("customPages", [])
    if not isinstance(custom_pages, list) or len(custom_pages) > 8:
        raise ConfigError("customPages deve ter no máximo oito páginas")
    result["customPages"] = [_custom_page(item, index) for index, item in enumerate(custom_pages)]
    custom_ids = [item["id"] for item in result["customPages"]]
    if len(custom_ids) != len(set(custom_ids)):
        raise ConfigError("id de página personalizada duplicado")

    page_by_id = catalog_by_id(result["customPages"])

    requested_pages = payload.get("pages", result["pages"])
    if not isinstance(requested_pages, list):
        raise ConfigError("pages deve ser uma lista")

    normalized_pages = []
    seen = set()
    for item in requested_pages:
        if not isinstance(item, dict):
            raise ConfigError("cada página deve ser um objeto")
        page_id = item.get("id")
        if page_id not in page_by_id:
            raise ConfigError(f"página desconhecida: {page_id!r}")
        if page_id in seen:
            raise ConfigError(f"página duplicada: {page_id}")
        seen.add(page_id)
        metadata = page_by_id[page_id]
        normalized_pages.append(
            {
                "id": page_id,
                "enabled": bool(item.get("enabled", metadata["defaultEnabled"])),
                "refreshSeconds": _bounded_int(
                    item.get("refreshSeconds", metadata["defaultRefreshSeconds"]),
                    f"pages.{page_id}.refreshSeconds",
                    metadata["minRefreshSeconds"],
                    metadata.get("maxRefreshSeconds", 3600),
                ),
            }
        )

    for metadata in page_by_id.values():
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
    if not isinstance(payload, dict):
        raise ConfigError("configuração deve ser um objeto JSON")
    normalized = normalize_config(payload)
    directory = state_dir(override)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        directory.chmod(0o700)
    except OSError:
        pass

    destination = config_path(override)
    descriptor, temporary = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            os.fchmod(file.fileno(), 0o600)
            file.write(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
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
