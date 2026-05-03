from __future__ import annotations

"""Minimal local configuration helpers for the MARS MVP."""

import json
import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"
CONFIG_DIR = PROJECT_ROOT / "config"


def load_local_env(env_path: Path | None = None) -> None:
    """Load key-value pairs from a local .env file if it exists.

    This keeps the MVP self-contained without requiring an extra dependency.
    Existing process environment variables always take precedence.
    """
    target = env_path or DEFAULT_ENV_PATH
    if not target.exists():
        return

    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_topic_markers() -> dict[str, list[str]]:
    """Load the canonical topic-marker dictionary from config/topic_markers.json."""
    target = CONFIG_DIR / "topic_markers.json"
    if not target.exists():
        return {}
    try:
        loaded = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {key: list(value) for key, value in loaded.items() if isinstance(value, list)}


def load_json_config(filename: str, default: dict[str, Any]) -> dict[str, Any]:
    """Load one JSON config from `config/`, falling back to the provided default."""
    target = CONFIG_DIR / filename
    if not target.exists():
        return default

    try:
        loaded = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default

    if not isinstance(loaded, dict):
        return default

    merged = dict(default)
    for key, value in loaded.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged
