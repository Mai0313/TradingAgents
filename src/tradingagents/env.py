"""Minimal .env loading for local CLI and programmatic runs."""

from __future__ import annotations

import os
from pathlib import Path

_LOADED = False


def load_dotenv_if_present(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from .env without overriding real environment vars."""
    global _LOADED  # noqa: PLW0603
    if _LOADED:
        return

    env_path = path or Path.cwd() / ".env"
    if not env_path.exists():
        _LOADED = True
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value

    _LOADED = True
