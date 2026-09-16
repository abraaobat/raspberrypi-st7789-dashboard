"""Local data providers with graceful fallbacks and no shell interpolation."""

from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path


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
    if routes:
        routes.sort(key=lambda row: row.get("metric") or 0)
        default_interface = routes[0].get("dev")

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
        "ethernetInterface": ethernet_interface,
        "ethernetIp": addresses.get(ethernet_interface) if ethernet_interface else None,
        "wifiInterface": wifi_interface,
        "wifiIp": addresses.get(wifi_interface) if wifi_interface else None,
        "wifiSsid": ssid,
        "wifiSignal": signal,
        "tailscaleIp": tailscale_ip,
    }


def throttling_status() -> str | None:
    raw = run(["vcgencmd", "get_throttled"])
    if not raw or "=" not in raw:
        return None
    try:
        flags = int(raw.split("=", 1)[1], 16)
    except ValueError:
        return None
    return "OK" if flags == 0 else f"0x{flags:x}"


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
            "throttling": throttling_status(),
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
