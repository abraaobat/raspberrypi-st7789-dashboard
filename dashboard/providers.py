"""Local data providers with graceful fallbacks and no shell interpolation."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from .credentials import CredentialError, CredentialStore
from .http_client import HTTP_TIMEOUT_SECONDS, MAX_JSON_BYTES, request_json, validate_source_url
from .integration_settings import INTEGRATION_IDS
from .integrations import fetch_integration
from .desk import DeskError, PomodoroStore, clock_snapshot
from .docker_monitor import fetch_docker
from .mqtt_monitor import fetch_mqtt


def run(command: list[str], timeout: float = 2.0) -> str | None:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def read_text(path: str | Path) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip("\0\n ")
    except OSError:
        return None


def _cpu_times() -> tuple[int, int] | None:
    raw = read_text("/proc/stat")
    if not raw:
        return None
    first = raw.splitlines()[0].split()
    if not first or first[0] != "cpu":
        return None
    try:
        values = [int(value) for value in first[1:]]
    except ValueError:
        return None
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle


class CpuSampler:
    def __init__(self):
        self.previous = None

    def read(self) -> float | None:
        current = _cpu_times()
        if current is None:
            return None
        if self.previous is None:
            self.previous = current
            time.sleep(0.08)
            current = _cpu_times()
            if current is None:
                return None
        total_delta = current[0] - self.previous[0]
        idle_delta = current[1] - self.previous[1]
        self.previous = current
        if total_delta <= 0:
            return 0.0
        return max(0.0, min(100.0, 100.0 * (total_delta - idle_delta) / total_delta))


def memory_percent() -> float | None:
    raw = read_text("/proc/meminfo")
    if not raw:
        return None
    values = {}
    for line in raw.splitlines():
        key, _, value = line.partition(":")
        try:
            values[key] = int(value.strip().split()[0])
        except (IndexError, ValueError):
            continue
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if not total or available is None:
        return None
    return max(0.0, min(100.0, 100.0 * (total - available) / total))


def temperature_celsius() -> float | None:
    raw = read_text("/sys/class/thermal/thermal_zone0/temp")
    if raw:
        try:
            value = float(raw)
            return value / 1000 if value > 1000 else value
        except ValueError:
            pass
    raw = run(["vcgencmd", "measure_temp"])
    if raw and "=" in raw:
        try:
            return float(raw.split("=", 1)[1].replace("'C", ""))
        except ValueError:
            pass
    return None


def uptime_label() -> str | None:
    raw = read_text("/proc/uptime")
    if not raw:
        return None
    try:
        seconds = float(raw.split()[0])
    except (IndexError, ValueError):
        return None
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return f"{days}d {hours}h"
    return f"{hours}h {minutes:02d}m"


def _json_command(command: list[str]) -> list:
    raw = run(command)
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def network_snapshot() -> dict:
    address_rows = _json_command(["ip", "-j", "-4", "addr", "show"])
    routes = _json_command(["ip", "-j", "route", "show", "default"])

    addresses = {}
    for row in address_rows:
        interface = row.get("ifname")
        candidates = [
            item.get("local")
            for item in row.get("addr_info", [])
            if item.get("family") == "inet" and item.get("scope") == "global"
        ]
        if interface and candidates:
            addresses[interface] = candidates[0]

    default_interface = None
    gateway = None
    if routes:
        routes.sort(key=lambda row: row.get("metric") or 0)
        default_interface = routes[0].get("dev")
        gateway = routes[0].get("gateway")

    ethernet_interfaces = [name for name in addresses if name.startswith(("eth", "en"))]
    wifi_interfaces = [
        name
        for name in addresses
        if name.startswith("wl") or Path(f"/sys/class/net/{name}/wireless").exists()
    ]

    ethernet_interface = next(
        (name for name in ethernet_interfaces if name == default_interface),
        ethernet_interfaces[0] if ethernet_interfaces else None,
    )
    wifi_interface = next(
        (name for name in wifi_interfaces if name == default_interface),
        wifi_interfaces[0] if wifi_interfaces else None,
    )

    ssid = None
    signal = None
    if wifi_interface:
        ssid = run(["iwgetid", wifi_interface, "--raw"])
        link = run(["iw", "dev", wifi_interface, "link"])
        if link:
            for line in link.splitlines():
                stripped = line.strip()
                if stripped.startswith("signal:"):
                    signal = stripped.split(":", 1)[1].strip()
                    break

    tailscale_ip = None
    tailscale = run(["tailscale", "ip", "-4"])
    if tailscale:
        tailscale_ip = tailscale.splitlines()[0]

    return {
        "defaultInterface": default_interface,
        "gateway": gateway,
        "ethernetInterface": ethernet_interface,
        "ethernetIp": addresses.get(ethernet_interface) if ethernet_interface else None,
        "wifiInterface": wifi_interface,
        "wifiIp": addresses.get(wifi_interface) if wifi_interface else None,
        "wifiSsid": ssid,
        "wifiSignal": signal,
        "tailscaleIp": tailscale_ip,
    }


def ping_milliseconds(host: str | None) -> float | None:
    if not host:
        return None
    raw = run(["ping", "-c", "1", "-W", "1", host], timeout=2.0)
    if not raw:
        return None
    match = re.search(r"time[=<]([0-9.]+)\s*ms", raw)
    return float(match.group(1)) if match else None


def service_statuses(services: list[str]) -> list[dict]:
    statuses = []
    for name in services:
        status = run(["systemctl", "is-active", name], timeout=2.0) or "offline"
        statuses.append({"name": name.removesuffix(".service"), "status": status})
    return statuses


def throttling_details() -> tuple[str | None, str | None]:
    raw = run(["vcgencmd", "get_throttled"])
    if not raw or "=" not in raw:
        return None, None
    try:
        flags = int(raw.split("=", 1)[1], 16)
    except ValueError:
        return None, None
    raw_label = f"0x{flags:x}"
    if flags == 0:
        return "OK", raw_label
    if flags & 0xF:
        return "ALERTA", raw_label
    if flags & 0xF0000:
        return "HISTÓRICO", raw_label
    return raw_label, raw_label


def throttling_status() -> str | None:
    return throttling_details()[0]


def usb_count() -> int | None:
    raw = run(["lsusb"])
    if raw is None:
        return None
    return len(raw.splitlines())


class SystemCollector:
    def __init__(self):
        self.cpu = CpuSampler()

    def collect(self) -> dict:
        model = read_text("/proc/device-tree/model")
        if model:
            model = model.replace("Raspberry Pi ", "RPi ")
        try:
            disk = shutil.disk_usage("/")
            disk_percent = 100.0 * disk.used / disk.total if disk.total else None
        except OSError:
            disk_percent = None

        throttling, throttling_raw = throttling_details()
        return {
            "cpuPercent": self.cpu.read(),
            "ramPercent": memory_percent(),
            "temperatureC": temperature_celsius(),
            "uptime": uptime_label(),
            "diskPercent": disk_percent,
            "hostname": socket.gethostname(),
            "network": network_snapshot(),
            "model": model or platform.machine(),
            "kernel": platform.release(),
            "usbCount": usb_count(),
            "spi": Path("/dev/spidev0.0").exists(),
            "throttling": throttling,
            "throttlingRaw": throttling_raw,
        }


class MetricsCache:
    def __init__(self, collector: SystemCollector | None = None):
        self.collector = collector or SystemCollector()
        self.value = None
        self.collected_at = 0.0
        self._lock = threading.Lock()

    def get(self, maximum_age: float = 1.0) -> dict:
        with self._lock:
            now = time.monotonic()
            if self.value is None or now - self.collected_at >= maximum_age:
                self.value = self.collector.collect()
                self.collected_at = now
            return dict(self.value)


def fetch_json(url: str, *, timeout: float = HTTP_TIMEOUT_SECONDS) -> dict | list:
    return request_json(url, timeout=timeout)


def json_path(payload, path: str):
    value = payload
    for token in path.split("."):
        if isinstance(value, list):
            try:
                value = value[int(token)]
            except (ValueError, IndexError) as exc:
                raise ValueError(f"caminho JSON não encontrado: {path}") from exc
        elif isinstance(value, dict) and token in value:
            value = value[token]
        else:
            raise ValueError(f"caminho JSON não encontrado: {path}")
    if isinstance(value, (dict, list)):
        raise ValueError(f"caminho JSON deve terminar em um valor simples: {path}")
    return value


def fetch_weather(settings: dict) -> dict:
    query = urlencode(
        {
            "latitude": settings["latitude"],
            "longitude": settings["longitude"],
            "current": "temperature_2m,apparent_temperature,is_day,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto",
            "forecast_days": 1,
        }
    )
    payload = fetch_json(f"https://api.open-meteo.com/v1/forecast?{query}")
    if not isinstance(payload, dict):
        raise ValueError("resposta meteorológica inválida")
    current = payload.get("current") or {}
    daily = payload.get("daily") or {}

    def first(name):
        values = daily.get(name) or []
        return values[0] if values else None

    def number(value):
        if value is None or isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    return {
        "configured": True,
        "locationName": settings.get("locationName") or "LOCAL",
        "temperatureC": number(current.get("temperature_2m")),
        "apparentC": number(current.get("apparent_temperature")),
        "weatherCode": number(current.get("weather_code")),
        "isDay": bool(current.get("is_day", 1)),
        "maximumC": number(first("temperature_2m_max")),
        "minimumC": number(first("temperature_2m_min")),
        "precipitationProbability": number(first("precipitation_probability_max")),
    }


def fetch_custom_page(definition: dict) -> dict:
    source = definition["source"]
    payload = fetch_json(source["url"])
    return extract_custom_values(payload, source["valuePath"], source.get("secondaryPath"))


def extract_custom_values(payload, value_path: str, secondary_path: str | None = None) -> dict:
    """Shared scalar extraction for real responses and offline examples."""
    value = json_path(payload, value_path)
    secondary = json_path(payload, secondary_path) if secondary_path else None

    def bounded(item):
        if isinstance(item, str) and len(item) > 160:
            return item[:157] + "..."
        return item

    return {"value": bounded(value), "secondary": bounded(secondary)}


def collect_sysops(snapshot: dict, settings: dict) -> dict:
    network = snapshot.get("network") or {}
    gateway = network.get("gateway")
    return {
        "diskPercent": snapshot.get("diskPercent"),
        "gateway": gateway,
        "pingMs": ping_milliseconds(gateway),
        "throttling": snapshot.get("throttling"),
        "throttlingRaw": snapshot.get("throttlingRaw"),
        "services": service_statuses(settings.get("services") or []),
    }


class AsyncDataCache:
    """Non-blocking stale-while-revalidate cache for external integrations."""

    def __init__(self):
        self._lock = threading.Lock()
        self._items: dict[str, dict] = {}

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)

    def get(self, key: str, signature: str, maximum_age: float, loader) -> dict:
        now = time.monotonic()
        with self._lock:
            item = self._items.get(key)
            if item is None or item["signature"] != signature:
                item = {
                    "signature": signature,
                    "value": None,
                    "error": None,
                    "loadedAt": 0.0,
                    "updatedAt": None,
                    "refreshing": False,
                    "retryAt": 0.0,
                }
                self._items[key] = item
            stale = item["value"] is None or now - item["loadedAt"] >= maximum_age
            if stale and not item["refreshing"] and now >= item["retryAt"]:
                item["refreshing"] = True
                thread = threading.Thread(
                    target=self._refresh,
                    args=(key, signature, loader),
                    daemon=True,
                    name=f"dashboard-provider-{key}",
                )
                thread.start()
            result = dict(item["value"] or {})
            result.update(
                {
                    "loading": item["value"] is None and item["refreshing"],
                    "stale": stale and item["value"] is not None,
                    "error": item["error"],
                    "updatedAt": item["updatedAt"],
                }
            )
            return result

    def _refresh(self, key: str, signature: str, loader) -> None:
        try:
            value = loader()
            error = None
        except Exception as exc:  # external providers must never stop the display loop
            value = None
            error = str(exc)
        with self._lock:
            item = self._items.get(key)
            if item is None or item["signature"] != signature:
                return
            if value is not None:
                item["value"] = value
                item["loadedAt"] = time.monotonic()
                item["updatedAt"] = datetime.now(timezone.utc).isoformat()
            item["error"] = error
            item["refreshing"] = False
            item["retryAt"] = time.monotonic() + (30 if error else 0)


class DataHub:
    """Route one page to only the providers that it needs."""

    def __init__(self, metrics: MetricsCache | None = None, state_override=None):
        self.metrics = metrics or MetricsCache()
        self.external = AsyncDataCache()
        self.credentials = CredentialStore(state_override)
        self.pomodoro = PomodoroStore(state_override)

    @staticmethod
    def _signature(value: dict) -> str:
        return json.dumps(value, sort_keys=True, ensure_ascii=True)

    def get(self, config: dict, page_id: str, maximum_age: float = 1.0) -> dict:
        # Time pages do not need a CPU/system scan or any network integration.
        if page_id == "mqtt":
            settings = config["mqtt"]
            try:
                metadata = self.credentials.status("mqtt", settings["brokerUrl"])
                if metadata["credentialConfigured"] and not metadata["credentialMatches"]:
                    raise CredentialError("a credencial MQTT pertence a outro broker; guarde a correta ou remova-a para acesso anônimo")
                revision = self.credentials.revision("mqtt", settings["brokerUrl"])
            except ValueError as exc:
                self.external.invalidate("mqtt")
                return {"mqtt": {"error": str(exc), "configured": False}}
            signature = self._signature({"settings": settings, "credentialRevision": revision})
            return {"mqtt": self.external.get("mqtt", signature, max(15, maximum_age),
                    lambda: fetch_mqtt(settings, self.credentials.read_secret("mqtt", settings["brokerUrl"]) if revision else None))}
        if page_id == "docker":
            settings = config["docker"]
            return {"docker": self.external.get(
                "docker", self._signature(settings), max(15, maximum_age),
                lambda: fetch_docker(settings),
            )}
        if page_id == "clock":
            return {"clock": clock_snapshot(config["clock"])}
        if page_id == "pomodoro":
            try:
                return {"pomodoro": self.pomodoro.snapshot(config["pomodoro"]["minutes"])}
            except DeskError as exc:
                return {"pomodoro": {"error": str(exc), "status": "unavailable"}}
        snapshot = self.metrics.get(maximum_age)
        if page_id == "weather":
            settings = config["weather"]
            if settings.get("latitude") is None or settings.get("longitude") is None:
                snapshot["weather"] = {"configured": False, "loading": False}
            else:
                snapshot["weather"] = self.external.get(
                    "weather",
                    self._signature(settings),
                    settings["refreshMinutes"] * 60,
                    lambda: fetch_weather(settings),
                )
        elif page_id == "sysops":
            settings = config["sysops"]
            signature = self._signature({"settings": settings, "network": snapshot.get("network")})
            snapshot["sysops"] = self.external.get(
                "sysops",
                signature,
                max(5, maximum_age),
                lambda: collect_sysops(snapshot, settings),
            )
        elif page_id in INTEGRATION_IDS:
            settings = config["integrations"][page_id]
            address = settings["baseUrl"]
            error = None
            try:
                revision = self.credentials.revision(page_id, address) if address else None
            except CredentialError as exc:
                revision = None
                error = str(exc)
            if not revision:
                self.external.invalidate(page_id)
                snapshot[page_id] = {
                    "configured": False,
                    "error": error or ("Guarde a credencial no painel." if address else "Configure a integração no painel."),
                }
            else:
                signature = self._signature({"settings": settings, "credentialRevision": revision})
                snapshot[page_id] = self.external.get(
                    page_id, signature, maximum_age,
                    lambda: fetch_integration(page_id, settings, self.credentials.read_secret(page_id, address)),
                )
        elif page_id.startswith("custom:"):
            definition = next(
                (item for item in config["customPages"] if item["id"] == page_id),
                None,
            )
            if definition:
                snapshot["custom"] = self.external.get(
                    page_id,
                    self._signature(definition),
                    max(10, maximum_age),
                    lambda: fetch_custom_page(definition),
                )
        return snapshot
