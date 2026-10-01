"""Scrub secrets and service ids from anything trinity prints."""

from __future__ import annotations

import re

_SECRETS = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}"),
    re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\b(?:gh[pousr]_|github_pat_|glpat-|xox[abpr]-)[A-Za-z0-9_-]{16,}"),
    re.compile(
        r"(?i)\b((?:auth_token|notary_token|(?:access|refresh|id|session|gateway)?_?token)|api[_-]?key|secret|password|cookie)"
        r"(\"?\s*[:=]\s*\"?)[^\s\",}]+"
    ),
)
_OPAQUE = re.compile(r"[A-Za-z0-9_+=-]{32,}")
_IDS = (
    re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
    re.compile(r"\b(?:room|thread|tbo|conv|acct|account|user|msg|aeon|env|agent|bot)[_-][A-Za-z0-9_-]{8,}\b"),
)


def _secret_sub(match: re.Match) -> str:
    if match.lastindex and match.lastindex >= 2:
        return f"{match.group(1)}{match.group(2)}***"
    return "***"


def _opaque_sub(match: re.Match) -> str:
    text = match.group(0)
    mixed = any(c.isdigit() for c in text) and any(c.isupper() for c in text) and any(c.islower() for c in text)
    return "***" if mixed else text


def scrub(text: str) -> str:
    """Remove token-like strings. Safe for message bodies (hashes and paths survive)."""
    for pattern in _SECRETS:
        text = pattern.sub(_secret_sub, text)
    return _OPAQUE.sub(_opaque_sub, text)


def scrub_ids(text: str) -> str:
    """scrub() plus account, room, bot, and message ids. Use for errors and hints."""
    text = scrub(text)
    for pattern in _IDS:
        text = pattern.sub("<id>", text)
    return text


def short_error(stderr: str, limit: int = 200) -> str:
    lines = [line.strip() for line in stderr.strip().splitlines() if line.strip()]
    text = lines[-1] if lines else ""
    text = scrub_ids(text)
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text
