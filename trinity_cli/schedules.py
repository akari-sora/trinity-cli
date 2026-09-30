"""Turn seat payloads into schedule rows and spot duplicates across seats."""

from __future__ import annotations

from trinity_cli.model import ScheduleItem

_LIST_KEYS = ("items", "automations", "data", "schedules", "routines")
_TITLE_KEYS = ("title", "name", "display_name", "label")
_WHEN_KEYS = ("when", "schedule", "cron", "cadence", "rrule", "time")
_WHEN_INNER = ("expression", "cron", "display", "text", "when", "time", "label")
_NEXT_KEYS = ("next_run_at", "nextRunAt", "next_run")


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def schedule_rows(payload: object) -> list[dict]:
    """Accept a bare list, `{items: [...]}`, or chatgpt-dot-cli's `{status, body}` envelope."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    body = payload.get("body")
    for source in (body, payload):
        if isinstance(source, list):
            return [row for row in source if isinstance(row, dict)]
        if not isinstance(source, dict):
            continue
        for key in _LIST_KEYS:
            rows = source.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _when(row: dict) -> str:
    for key in _WHEN_KEYS:
        value = row.get(key)
        if _text(value):
            return _text(value)
        if isinstance(value, dict):
            for inner in _WHEN_INNER:
                if _text(value.get(inner)):
                    return _text(value.get(inner))
    for key in _NEXT_KEYS:
        if _text(row.get(key)):
            return _text(row.get(key))
    return ""


def schedule_item(row: dict) -> ScheduleItem:
    title = ""
    for key in _TITLE_KEYS:
        title = _text(row.get(key))
        if title:
            break
    if not title:
        for key in ("prompt", "instructions", "description"):
            raw = _text(row.get(key))
            if raw:
                title = raw.splitlines()[0].strip()
                break
    status = _text(row.get("status") or row.get("state"))
    if not status and isinstance(row.get("enabled"), bool):
        status = "enabled" if row["enabled"] else "disabled"
    return ScheduleItem(title=title or "（沒有標題）", when=_when(row), status=status)


def parse_schedules(payload: object) -> list[ScheduleItem]:
    return [schedule_item(row) for row in schedule_rows(payload)]


def _norm(text: str) -> str:
    return " ".join(text.casefold().split())


def duplicate_groups(found: list[tuple[str, ScheduleItem]]) -> list[dict]:
    """Same title on two seats is a duplicate. Same time as well is called out."""
    groups: dict[str, list[tuple[str, ScheduleItem]]] = {}
    for label, item in found:
        key = _norm(item.title)
        if not key or key == _norm("（沒有標題）"):
            continue
        groups.setdefault(key, []).append((label, item))
    duplicates = []
    for members in groups.values():
        seats = []
        for label, _ in members:
            if label not in seats:
                seats.append(label)
        if len(seats) < 2:
            continue
        times = {_norm(item.when) for _, item in members if _norm(item.when)}
        duplicates.append(
            {
                "title": members[0][1].title,
                "seats": seats,
                "same_time": len(times) == 1 and all(_norm(item.when) for _, item in members),
            }
        )
    return duplicates
