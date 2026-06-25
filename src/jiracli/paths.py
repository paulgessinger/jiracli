"""Filesystem locations for jiracli (config + data)."""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

APP_NAME = "jiracli"


def config_dir() -> Path:
    """Directory holding ``config.toml``. Created on access."""
    path = Path(user_config_dir(APP_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    """Directory holding the SQLite database. Created on access."""
    path = Path(user_data_dir(APP_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_file() -> Path:
    return config_dir() / "config.toml"


def db_file() -> Path:
    return data_dir() / "jiracli.db"
