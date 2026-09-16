"""Owner-only, write-only-to-the-web credential store. Not disk encryption."""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import stat
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .config import state_dir
from .integration_settings import INTEGRATION_IDS, base_url


class CredentialError(ValueError):
    """Safe, secret-free error that may be shown in the local panel."""


def validate_secret(connector: str, value) -> str:
    if connector not in INTEGRATION_IDS:
        raise CredentialError("integração não suportada")
    if not isinstance(value, str) or not 1 <= len(value) <= 4096:
        raise CredentialError("informe uma credencial de até 4096 caracteres")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise CredentialError("a credencial não pode conter caracteres de controle")
    if connector == "homeassistant" and (not value.isascii() or any(char.isspace() for char in value)):
        raise CredentialError("o token do Home Assistant deve ser copiado inteiro, sem espaços")
    return value


class CredentialStore:
    def __init__(self, override: str | Path | None = None):
        self.directory = state_dir(override)
        self.path = self.directory / "credentials.json"
        self.lock_path = self.directory / ".credentials.lock"

    @contextmanager
    def _locked(self):
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.directory.chmod(0o700)
            descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "a") as lock:
                details = os.fstat(lock.fileno())
                if not stat.S_ISREG(details.st_mode) or details.st_uid != os.geteuid():
                    raise CredentialError("arquivo de bloqueio do cofre inválido")
                os.fchmod(lock.fileno(), 0o600)
                fcntl.flock(lock, fcntl.LOCK_EX)
                yield
        except OSError as exc:
            raise CredentialError("não foi possível acessar o cofre local") from exc

    def _read(self):
        try:
            descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return {"schemaVersion": 1, "entries": {}}
        try:
            with os.fdopen(descriptor, "r", encoding="utf-8") as file:
                details = os.fstat(file.fileno())
                if not stat.S_ISREG(details.st_mode) or details.st_uid != os.geteuid() or details.st_mode & 0o077:
                    raise CredentialError("o cofre precisa pertencer ao usuário e ter permissão 0600")
                if details.st_size > 32 * 1024:
                    raise CredentialError("cofre inválido; preserve o arquivo para recuperação local")
                payload = json.loads(file.read(32 * 1024))
            if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
                raise ValueError()
            entries = payload["entries"]
            if not isinstance(entries, dict) or set(entries) - set(INTEGRATION_IDS):
                raise ValueError()
            for connector, entry in entries.items():
                if not isinstance(entry, dict):
                    raise ValueError()
                validate_secret(connector, entry["secret"])
                if base_url(entry["baseUrl"], required=True) != entry["baseUrl"]:
                    raise ValueError()
                if not isinstance(entry["revision"], str) or not isinstance(entry["updatedAt"], str):
                    raise ValueError()
            return payload
        except (KeyError, TypeError, ValueError, UnicodeError) as exc:
            if isinstance(exc, CredentialError):
                raise
            raise CredentialError("cofre inválido; preserve o arquivo para recuperação local") from exc

    def _write(self, payload):
        descriptor, temporary = tempfile.mkstemp(prefix=".credentials-", suffix=".tmp", dir=self.directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                os.fchmod(file.fileno(), 0o600)
                json.dump(payload, file, ensure_ascii=False)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def put(self, connector: str, address: str, secret) -> dict:
        value = validate_secret(connector, secret)
        address = base_url(address, required=True)
        with self._locked():
            payload = self._read()  # A corrupt vault is never silently overwritten.
            payload["entries"][connector] = {
                "baseUrl": address,
                "secret": value,
                "revision": secrets.token_hex(16),
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            }
            self._write(payload)
        return self.status(connector, address)

    def delete(self, connector: str):
        if connector not in INTEGRATION_IDS:
            raise CredentialError("integração não suportada")
        with self._locked():
            payload = self._read()
            if connector in payload["entries"]:
                del payload["entries"][connector]
                self._write(payload)

    def status(self, connector: str, address: str = "") -> dict:
        if connector not in INTEGRATION_IDS:
            raise CredentialError("integração não suportada")
        with self._locked():
            entry = self._read()["entries"].get(connector)
            return {
                "credentialConfigured": entry is not None,
                "credentialMatches": bool(entry and entry["baseUrl"] == address),
                "credentialBaseUrl": entry["baseUrl"] if entry else None,
                "updatedAt": entry["updatedAt"] if entry else None,
            }

    def revision(self, connector: str, address: str) -> str | None:
        with self._locked():
            entry = self._read()["entries"].get(connector)
            return entry["revision"] if entry and entry["baseUrl"] == address else None

    def read_secret(self, connector: str, address: str) -> str:
        """Internal only: never use this return value in API responses or signatures."""
        with self._locked():
            entry = self._read()["entries"].get(connector)
            if not entry or entry["baseUrl"] != address:
                raise CredentialError("guarde uma credencial para este endereço da integração")
            return entry["secret"]
