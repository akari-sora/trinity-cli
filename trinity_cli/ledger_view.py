"""Read the send ledger. This command only reads."""

from __future__ import annotations

from trinity_cli.redact import scrub
from trinity_cli.shown import Shown
from trinity_cli.state import Ledger
from trinity_cli.util import local_stamp, one_line, parse_since, parse_time

_HIDDEN = {"reply_key", "message_key"}


def _match_status(record: dict, status: str) -> bool:
    wanted = status.casefold()
    for key in ("event", "reply", "readback", "status", "delivery"):
        value = record.get(key)
        if isinstance(value, str) and value.casefold() == wanted:
            return True
    return False


def _public(record: dict) -> dict:
    cleaned = {}
    for key, value in record.items():
        if key in _HIDDEN:
            continue
        cleaned[key] = scrub(value) if isinstance(value, str) else value
    return cleaned


def _line(record: dict) -> str:
    stamp = local_stamp(parse_time(record.get("at")) or parse_time(record.get("sent_at")))
    event = record.get("reply") or record.get("status") or record.get("event") or ""
    parts = [stamp, str(event), str(record.get("seat") or ""), str(record.get("target") or "")]
    if record.get("readback"):
        parts.append(str(record["readback"]))
    line = "  ".join(parts)
    if record.get("error"):
        line += "  " + one_line(str(record["error"]), 120)
    return scrub(line)


def run_log(ledger: Ledger, *, seat: str | None = None, since: str | None = None, status: str | None = None, limit: int = 50) -> Shown:
    try:
        cutoff = parse_since(since) if since else None
    except ValueError as exc:
        return Shown(2, str(exc), {"error": str(exc), "records": []})
    if limit < 1:
        return Shown(2, "--limit 至少要 1。", {"error": "bad limit", "records": []})
    chosen = []
    for record in ledger.records():
        if not isinstance(record, dict):
            continue
        if seat and record.get("seat") != seat:
            continue
        if status and not _match_status(record, status):
            continue
        if cutoff is not None:
            at = parse_time(record.get("at")) or parse_time(record.get("sent_at"))
            if at is None or at < cutoff:
                continue
        chosen.append(record)
    shown = [_public(record) for record in chosen[-limit:]]
    if not shown:
        text = "沒有紀錄。"
    else:
        text = "\n".join(_line(record) for record in shown)
    return Shown(0, text, {"records": shown})
