"""Atomic runtime control and display-state files shared across services."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from .config import state_dir


def _read(path: Path, fallback: dict) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else dict(fallback)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return dict(fallback)


def _write(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    os.replace(temporary, path)


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


class RuntimeStore:
    def __init__(self, override: str | Path | None = None):
        directory = state_dir(override)
        self.control_path = directory / "control.json"
        self.display_path = directory / "display-state.json"

    def read_control(self) -> dict:
        return _read(self.control_path, {"requestedPage": None, "updatedAt": None})

    def request_page(self, page_id: str):
        _write(self.control_path, {"requestedPage": page_id, "updatedAt": _timestamp()})

    def read_display(self) -> dict:
        return _read(
            self.display_path,
            {"currentPage": None, "lastRenderAt": None, "error": None},
        )

    def update_display(self, page_id: str, error: str | None = None):
        _write(
            self.display_path,
            {
                "currentPage": page_id,
                "lastRenderAt": _timestamp(),
                "error": error,
            },
        )
