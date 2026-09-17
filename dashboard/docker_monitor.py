"""Optional, bounded Docker Engine queries over a local Unix socket only.

The browser cannot choose sockets, API paths or methods. This module never
changes Docker permissions and never calls a mutating Engine endpoint.
Access to the daemon itself can still be privileged: see docs/DOCKER_MONITOR.md.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import socket
import stat
import threading
import time

MAX_DOCKER_BYTES = 256 * 1024
MAX_CONTAINERS = 256
DOCKER_TIMEOUT_SECONDS = 4
DEFAULT_SOCKET = "/var/run/docker.sock"
NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
API_PATTERN = re.compile(r"1\.[0-9]{1,3}$")
STATES = {"created", "running", "paused", "restarting", "removing", "exited", "dead"}


class DockerError(ValueError):
    """A safe, user-facing diagnostic, never a raw daemon response."""


def docker_settings(payload) -> dict:
    if not isinstance(payload, dict) or set(payload) - {"names"}:
        raise DockerError("docker aceita somente uma lista de nomes")
    names = payload.get("names", [])
    if not isinstance(names, list) or len(names) > 4:
        raise DockerError("docker.names deve ter no máximo quatro nomes")
    result = []
    for name in names:
        if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name.strip()):
            raise DockerError("nome de contêiner inválido; use letras, números, ponto, hífen ou sublinhado")
        name = name.strip()
        if name not in result:
            result.append(name)
    return {"names": result}


def socket_path() -> str:
    # Operator-only environment, not config.json, query parameters or DOCKER_HOST.
    value = os.environ.get("ST7789_DOCKER_SOCKET", DEFAULT_SOCKET)
    if not os.path.isabs(value) or "\0" in value:
        raise DockerError("socket Docker local inválido")
    try:
        mode = os.stat(value).st_mode
    except FileNotFoundError:
        raise DockerError("Docker não disponível: socket local não encontrado") from None
    except PermissionError:
        raise DockerError("Sem permissão para consultar o socket Docker") from None
    except OSError:
        raise DockerError("Socket Docker local indisponível") from None
    if not stat.S_ISSOCK(mode):
        raise DockerError("O destino Docker deve ser um socket Unix local")
    return value


class _UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path, timeout):
        super().__init__("localhost", timeout=timeout)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        try:
            self.sock.connect(self.path)
        except Exception:
            self.sock.close()
            raise


def _get_json(path: str, endpoint: str, deadline: float):
    if endpoint != "/version" and not re.fullmatch(r"/v1\.[0-9]{1,3}/containers/json\?all=1", endpoint):
        raise DockerError("Consulta Docker não permitida")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise DockerError("Tempo limite da consulta Docker excedido")
    connection = _UnixHTTP(path, remaining)
    response = None
    watchdog = None
    try:
        connection.connect()
        transport = connection.sock

        def expire():
            try:
                transport.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        watchdog = threading.Timer(max(0.001, deadline - time.monotonic()), expire)
        watchdog.daemon = True
        watchdog.start()
        connection.request("GET", endpoint, headers={"Accept": "application/json", "Connection": "close"})
        response = connection.getresponse()
        if response.status in {401, 403}:
            raise DockerError("Sem permissão para consultar o Docker")
        if response.status != 200:
            raise DockerError("Docker indisponível ou versão de API incompatível")
        declared = response.getheader("Content-Length")
        if declared is not None:
            if len(declared) > 12 or not declared.isdigit() or int(declared) > MAX_DOCKER_BYTES:
                raise DockerError("Resposta Docker inválida ou maior que 256 KiB")
        chunks = []
        size = 0
        while True:
            # A complete HTTP/1.0 or Connection: close response closes its socket
            # after the last body chunk. Do not set a timeout on that closed fd.
            if response.isclosed():
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DockerError("Tempo limite da consulta Docker excedido")
            transport.settimeout(remaining)
            chunk = response.read1(min(8192, MAX_DOCKER_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_DOCKER_BYTES:
                raise DockerError("Resposta Docker maior que 256 KiB")
        if declared is not None and size != int(declared):
            raise DockerError("Resposta Docker incompleta")
        try:
            return json.loads(b"".join(chunks).decode("utf-8"))
        except (ValueError, UnicodeError, RecursionError):
            raise DockerError("Docker não retornou JSON válido") from None
    except PermissionError:
        raise DockerError("Sem permissão para consultar o socket Docker") from None
    except (OSError, http.client.HTTPException):
        raise DockerError("Docker indisponível ou tempo limite excedido") from None
    finally:
        if watchdog is not None:
            watchdog.cancel()
        if response is not None:
            response.close()
        connection.close()


def summarize_containers(payload, settings) -> dict:
    names = docker_settings(settings)["names"]
    if not isinstance(payload, list) or len(payload) > MAX_CONTAINERS:
        raise DockerError("Lista Docker inválida ou com mais de 256 contêineres")
    containers = []
    found = set()
    for item in payload:
        if not isinstance(item, dict):
            raise DockerError("Dados de contêiner inválidos")
        aliases = item.get("Names")
        if not isinstance(aliases, list) or not aliases or any(
            not isinstance(alias, str) or not re.fullmatch(r"/[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", alias)
            for alias in aliases
        ):
            raise DockerError("Nomes de contêiner inválidos")
        aliases = [alias[1:] for alias in aliases]
        matches = [name for name in names if name in aliases]
        if names and not matches:
            continue
        found.update(matches)
        state = item.get("State")
        state = state if isinstance(state, str) and state in STATES else "unknown"
        status = item.get("Status")
        if not isinstance(status, str):
            status = ""
        health_match = re.search(r"\((healthy|unhealthy|health: starting)\)", status[:512])
        health = {"health: starting": "starting"}.get(health_match[1], health_match[1]) if health_match else "none"
        if state != "running":
            health = "none"
        containers.append({"name": matches[0] if matches else aliases[0], "state": state, "health": health})

    # Show unhealthy/restarting/dead before healthy containers. Stable name ordering
    # avoids randomly hiding a problem when Docker changes its response order.
    def priority(item):
        if item["health"] == "unhealthy" or item["state"] in {"dead", "restarting"}:
            return 0, item["name"]
        if item["state"] != "running" or item["health"] == "starting":
            return 1, item["name"]
        return 2, item["name"]

    containers.sort(key=priority)
    return {
        "available": True,
        "scope": "selected" if names else "all",
        "total": len(containers),
        "running": sum(item["state"] == "running" for item in containers),
        "stopped": sum(item["state"] in {"created", "exited", "dead"} for item in containers),
        "unhealthy": sum(item["health"] == "unhealthy" for item in containers),
        "other": sum(item["state"] in {"paused", "restarting", "removing", "unknown"} for item in containers),
        "containers": containers[:4],
        "hiddenCount": max(0, len(containers) - 4),
        "missingNames": [name for name in names if name not in found],
    }


def fetch_docker(settings) -> dict:
    settings = docker_settings(settings)
    path = socket_path()
    deadline = time.monotonic() + DOCKER_TIMEOUT_SECONDS
    version = _get_json(path, "/version", deadline)
    api = version.get("ApiVersion") if isinstance(version, dict) else None
    if not isinstance(api, str) or not API_PATTERN.fullmatch(api):
        raise DockerError("Docker informou versão de API inválida")
    return summarize_containers(_get_json(path, f"/v{api}/containers/json?all=1", deadline), settings)
