"""Path helpers for PowerWatcher."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "PowerWatcher"


def app_root() -> Path:
    """Directory that contains run.pyw."""
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Per-user writable directory: %LOCALAPPDATA%\\PowerWatcher."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return data_dir() / "config.json"


def db_path() -> Path:
    return data_dir() / "telemetry.db"


def log_path() -> Path:
    return data_dir() / "powerwatcher.log"
