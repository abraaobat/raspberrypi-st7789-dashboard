"""Small local PIN store for the LAN control panel."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path

from .config import state_dir

ITERATIONS = 260_000


class AuthError(ValueError):
    pass


class LoginLimiter:
    """Small in-memory limiter suitable for a single local Waitress process."""

    def __init__(self, maximum_attempts: int = 5, window_seconds: int = 60):
        self.maximum_attempts = maximum_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allowed(self, client: str) -> bool:
        now = time.monotonic()
        with self._lock:
            recent = [
                attempted_at
                for attempted_at in self._attempts.get(client, [])
                if now - attempted_at < self.window_seconds
            ]
            self._attempts[client] = recent
            return len(recent) < self.maximum_attempts

    def record_failure(self, client: str):
        with self._lock:
            self._attempts.setdefault(client, []).append(time.monotonic())

    def clear(self, client: str):
        with self._lock:
            self._attempts.pop(client, None)


class AuthStore:
    def __init__(self, override: str | Path | None = None):
        self.directory = state_dir(override)
        self.auth_path = self.directory / "auth.json"
        self.secret_path = self.directory / "session-secret.bin"

    def _ensure_directory(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self.directory.chmod(0o700)
        except OSError:
            pass

    def configured(self) -> bool:
        try:
            payload = json.loads(self.auth_path.read_text(encoding="utf-8"))
            return bool(payload.get("salt") and payload.get("hash"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return False

    def setup(self, pin: str):
        if self.configured():
            raise AuthError("PIN já configurado")
        self._validate_pin(pin)
        salt = secrets.token_bytes(16)
        digest = self._derive(pin, salt)
        self._write_json(
            self.auth_path,
            {
                "schemaVersion": 1,
                "algorithm": "pbkdf2-sha256",
                "iterations": ITERATIONS,
                "salt": salt.hex(),
                "hash": digest.hex(),
            },
        )

    def verify(self, pin: str) -> bool:
        try:
            payload = json.loads(self.auth_path.read_text(encoding="utf-8"))
            salt = bytes.fromhex(payload["salt"])
            expected = bytes.fromhex(payload["hash"])
            iterations = int(payload.get("iterations", ITERATIONS))
        except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError, OSError):
            return False
        actual = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)

    def session_secret(self) -> bytes:
        self._ensure_directory()
        try:
            value = self.secret_path.read_bytes()
            if len(value) >= 32:
                return value
        except OSError:
            pass
        value = secrets.token_bytes(48)
        temporary = self.secret_path.with_suffix(".tmp")
        temporary.write_bytes(value)
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary, self.secret_path)
        return value

    @staticmethod
    def _validate_pin(pin: str):
        if not isinstance(pin, str) or not 4 <= len(pin) <= 64:
            raise AuthError("o PIN deve ter entre 4 e 64 caracteres")

    @staticmethod
    def _derive(pin: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, ITERATIONS)

    def _write_json(self, path: Path, payload: dict):
        self._ensure_directory()
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary, path)
