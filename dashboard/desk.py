"""Offline clock and process-shared Pomodoro using a monotonic deadline."""
from __future__ import annotations

import fcntl
import json
import math
import os
import platform
import re
import stat
import subprocess
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import state_dir
from .desk_settings import DeskError, clock_settings, pomodoro_settings


def clock_snapshot(settings, *, now=None):
    current = now or datetime.now().astimezone()
    if settings["timezone"]:
        current = current.astimezone(ZoneInfo(settings["timezone"]))
    pattern = "%H:%M" if settings["hour24"] else "%I:%M"
    if settings["showSeconds"]:
        pattern += ":%S"
    weekdays = ("SEGUNDA", "TERÇA", "QUARTA", "QUINTA", "SEXTA", "SÁBADO", "DOMINGO")
    return {"time": current.strftime(pattern), "date": current.strftime("%d/%m/%Y"),
            "weekday": weekdays[current.weekday()], "period": current.strftime("%p") if not settings["hour24"] else "",
            "timezone": settings["timezone"] or current.tzname() or "SISTEMA"}


@lru_cache(maxsize=1)
def system_boot_id():
    try:
        if platform.system() == "Linux":
            value = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            if re.fullmatch(r"[a-f0-9-]{36}", value):
                return value
        elif platform.system() == "Darwin":
            result = subprocess.run(["/usr/sbin/sysctl", "-n", "kern.bootsessionuuid"],
                                    capture_output=True, text=True, timeout=1, check=False)
            value = result.stdout.strip().lower()
            if result.returncode == 0 and re.fullmatch(r"[a-f0-9-]{36}", value):
                return "darwin-" + value
    except (OSError, subprocess.SubprocessError):
        pass
    return None  # Fail closed: no persistent running timer without boot identity.


def _number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and 0 <= value <= 10**15 and math.isfinite(value)


class PomodoroStore:
    def __init__(self, override=None, *, monotonic=None, boot_id=None):
        self.directory = state_dir(override)
        self.path = self.directory / "pomodoro.json"
        self.lock_path = self.directory / ".pomodoro.lock"
        self.now = monotonic or time.monotonic
        self.boot = boot_id if boot_id is not None else system_boot_id()

    @contextmanager
    def _locked(self):
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if stat.S_IMODE(self.directory.stat().st_mode) != 0o700:
                self.directory.chmod(0o700)
            descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            with os.fdopen(descriptor, "a") as lock:
                details = os.fstat(lock.fileno())
                if not stat.S_ISREG(details.st_mode) or details.st_uid != os.geteuid():
                    raise DeskError("arquivo de bloqueio do Pomodoro inválido")
                if stat.S_IMODE(details.st_mode) != 0o600:
                    os.fchmod(lock.fileno(), 0o600)
                fcntl.flock(lock, fcntl.LOCK_EX)
                yield
        except OSError:
            raise DeskError("não foi possível acessar o estado do Pomodoro") from None

    def _read(self, minutes):
        try:
            descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return {"schemaVersion": 1, "status": "idle", "totalSeconds": minutes * 60,
                    "remainingSeconds": minutes * 60, "deadline": None, "bootId": self.boot}
        try:
            with os.fdopen(descriptor, "r", encoding="utf-8") as file:
                details = os.fstat(file.fileno())
                if not stat.S_ISREG(details.st_mode) or details.st_uid != os.geteuid() or details.st_mode & 0o077 or details.st_size > 4096:
                    raise DeskError("estado do Pomodoro precisa ser privado e válido")
                record = json.loads(file.read(4097))
            if not isinstance(record, dict) or record.get("schemaVersion") != 1 or record.get("status") not in {"idle", "running", "paused"}:
                raise ValueError()
            total, remaining = record["totalSeconds"], record["remainingSeconds"]
            if not _number(total) or not 60 <= total <= 7200 or not _number(remaining) or remaining > total:
                raise ValueError()
            if record["status"] == "running" and not _number(record["deadline"]):
                raise ValueError()
            if record.get("bootId") is not None and (not isinstance(record["bootId"], str) or len(record["bootId"]) > 80):
                raise ValueError()
            return record
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise DeskError("estado do Pomodoro inválido; preserve o arquivo para recuperação local") from None

    def _snapshot(self, record, minutes):
        status = record["status"]
        total = minutes * 60 if status == "idle" else record["totalSeconds"]
        remaining = total if status == "idle" else record["remainingSeconds"]
        if status == "running":
            if not self.boot or record.get("bootId") != self.boot:
                status, remaining = "interrupted", None
            else:
                remaining = max(0, min(total, record["deadline"] - self.now()))
                if remaining <= 0:
                    status = "completed"
        return {"status": status, "totalSeconds": total,
                "remainingSeconds": math.ceil(remaining) if remaining is not None else None,
                "progress": max(0, min(1, 1 - remaining / total)) if remaining is not None else 0}

    def snapshot(self, minutes=25):
        self._validate_minutes(minutes)
        with self._locked():
            return self._snapshot(self._read(minutes), minutes)

    @staticmethod
    def _validate_minutes(minutes):
        pomodoro_settings({"minutes": minutes})

    def command(self, action, minutes=25):
        self._validate_minutes(minutes)
        if not isinstance(action, str) or action not in {"start", "pause", "resume", "reset"}:
            raise DeskError("ação do Pomodoro não permitida")
        with self._locked():
            record = self._read(minutes)
            view = self._snapshot(record, minutes)
            if action == "start":
                if view["status"] not in {"idle", "completed", "interrupted"}:
                    raise DeskError("há um ciclo em andamento; pause, retome ou reinicie")
                if not self.boot:
                    raise DeskError("não foi possível identificar a inicialização do sistema")
                record = {"schemaVersion": 1, "status": "running", "totalSeconds": minutes * 60,
                          "remainingSeconds": minutes * 60, "deadline": self.now() + minutes * 60, "bootId": self.boot}
            elif action == "pause":
                if view["status"] != "running":
                    raise DeskError("somente um ciclo em execução pode ser pausado")
                record["remainingSeconds"] = max(0, min(record["totalSeconds"], record["deadline"] - self.now()))
                record.update(status="paused", deadline=None)
            elif action == "resume":
                if view["status"] != "paused" or not self.boot:
                    raise DeskError("somente um ciclo pausado pode ser retomado")
                record.update(status="running", deadline=self.now() + record["remainingSeconds"], bootId=self.boot)
            else:
                record = {"schemaVersion": 1, "status": "idle", "totalSeconds": minutes * 60,
                          "remainingSeconds": minutes * 60, "deadline": None, "bootId": self.boot}
            descriptor, temporary = tempfile.mkstemp(prefix=".pomodoro-", suffix=".tmp", dir=self.directory)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                    os.fchmod(file.fileno(), 0o600)
                    json.dump(record, file)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return self._snapshot(record, minutes)
