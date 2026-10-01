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
    return clean_account(_config().get("gbot_account"))


def clean_bot_name(value: object) -> str | None:
    """A bot name. Tokens and email-shaped labels are refused."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > 80 or any(ch in text for ch in "\r\n\t"):
        return None
    if "@" in text or text.startswith("eyJ") or text.startswith("sk-") or "token" in text.lower():
        return None
    return text


def configured_grok_bot() -> str | None:
    """TRINITY_GROK_BOT wins over ~/.trinity-cli/config.json key grok_bot."""
    if os.environ.get("TRINITY_GROK_BOT"):
        return clean_bot_name(os.environ.get("TRINITY_GROK_BOT"))
    return clean_bot_name(_config().get("grok_bot"))


def _config() -> dict:
    path = home() / "config.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
