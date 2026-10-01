"""Time parsing, display, and the delivery nonce."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

NONCE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
NONCE_LENGTH = 6
# Passed as a cursor id so read() returns the current window. Never saved.
WINDOW_CURSOR_ID = "trinity-window"
WINDOW_CURSOR = {"id": WINDOW_CURSOR_ID, "at": "1970-01-01T00:00:00+00:00"}


def decode_text(raw: bytes) -> str:
    """UTF-8 with or without a BOM, or UTF-16 with a BOM (what PowerShell 5.1 `>` writes)."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: object) -> datetime | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 1e11 else value
        try:
            return datetime.fromtimestamp(seconds, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.isdigit():
            return parse_time(int(text))
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def local_stamp(value: datetime | None) -> str:
    if value is None:
        return "時間不明"
    return value.astimezone().strftime("%m-%d %H:%M")


_SINCE = re.compile(r"^(\d+)\s*([mhdw])$")


def parse_since(text: str, now: datetime | None = None) -> datetime:
    """`30m`, `2h`, `1d`, `1w`, or an ISO date/time (local time when no zone is given)."""
    now = now or now_utc()
    match = _SINCE.match(text.strip().lower())
    if match:
        amount = int(match.group(1))
        unit = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}[match.group(2)]
        return now - timedelta(**{unit: amount})
    try:
        parsed = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"--since 看不懂：{text}（用 30m、2h、1d 或 2026-09-30T10:00）") from exc
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def one_line(text: str, limit: int = 0) -> str:
    text = " ".join(str(text).split())
    if limit and len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def new_nonce() -> str:
    return "".join(secrets.choice(NONCE_ALPHABET) for _ in range(NONCE_LENGTH))


def nonce_tag(nonce: str) -> str:
    return f"[trinity {nonce}]"


def with_nonce(text: str, nonce: str) -> str:
    """The message body stays untouched; the tag sits alone on the last line."""
    return f"{text.strip()}\n\n{nonce_tag(nonce)}"


def has_nonce(text: str, nonce: str) -> bool:
    return nonce_tag(nonce) in (text or "")
