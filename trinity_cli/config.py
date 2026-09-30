"""Local settings. Account names only; tokens are ignored."""

from __future__ import annotations

import json
import os

from trinity_cli.state import home

_MAX_ACCOUNT = 64


def clean_account(value: object) -> str | None:
    """A short account label. Anything that looks like a token is refused."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > _MAX_ACCOUNT or any(ch.isspace() for ch in text):
        return None
    if text.startswith("eyJ") or text.startswith("sk-") or "token" in text.lower():
        return None
    return text


def configured_gbot_account() -> str | None:
    """TRINITY_GBOT_ACCOUNT wins over ~/.trinity-cli/config.json key gbot_account."""
    from_env = clean_account(os.environ.get("TRINITY_GBOT_ACCOUNT"))
    if os.environ.get("TRINITY_GBOT_ACCOUNT"):
        return from_env
    path = home() / "config.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return clean_account(data.get("gbot_account"))
