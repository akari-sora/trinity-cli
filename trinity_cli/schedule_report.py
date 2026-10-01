"""List schedules and flag the same title on more than one seat."""

from __future__ import annotations

from trinity_cli.app import aggregate_exit, call, each
from trinity_cli.model import FAILED, OK, ScheduleItem
from trinity_cli.schedules import duplicate_groups
from trinity_cli.shown import Shown


def _items(value: object) -> list[ScheduleItem]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, ScheduleItem)]


def run_schedules(seats) -> Shown:
    reports = list(zip(seats, each(seats, lambda seat: call(seat, "schedules"))))
    lines: list[str] = []
    rows: list[tuple[str, ScheduleItem]] = []
    seats_json = []
    for seat, result in reports:
        if result.state == OK:
            items = _items(result.value)
            served = getattr(seat, "served_backend", "") or ""
            shown = seat.label
            if served:
                shown = f"{seat.label} · {served}"
                if getattr(seat, "fell_back", False):
                    shown += "（api 不支援，已改走 browser）"
            seats_json.append(
                {
                    "seat": seat.key,
                    "label": seat.label,
                    "state": result.state,
                    "backend": served,
                    "fallback": bool(getattr(seat, "fell_back", False)),
                    "items": [{"title": item.title, "when": item.when, "status": item.status} for item in items],
                }
            )
            lines.append(shown)
            if items:
                for item in items:
                    when = f" · {item.when}" if item.when else ""
                    status = f" · {item.status}" if item.status else ""
                    lines.append(f"  • {item.title}{when}{status}")
                    rows.append((seat.label, item))
            else:
                lines.append("  （沒有排程）")
        else:
            lines.append(f"{seat.label}  {'✗' if result.state == FAILED else '–'} {result.error}")
            seats_json.append({"seat": seat.key, "label": seat.label, "state": result.state, "error": result.error, "hint": result.hint})
        lines.append("")
    duplicates = duplicate_groups(rows)
    if duplicates:
        lines.append("可能重複：")
        for group in duplicates:
            where = "、".join(group["seats"])
            extra = "，標題和時間都一樣" if group["same_time"] else ""
            lines.append(f"  • 「{group['title']}」出現在 {where}{extra}")
    elif rows:
        lines.append("沒有看出跨座位的重複標題。")
    text = "\n".join(lines).rstrip()
    return Shown(aggregate_exit([result.state for _, result in reports]), text, {"seats": seats_json, "duplicates": duplicates})
