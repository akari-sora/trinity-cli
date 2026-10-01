"""One local brief. Push writes Grok instructions only, and only after confirmation."""

from __future__ import annotations

import difflib
from pathlib import Path

from trinity_cli.app import call
from trinity_cli.targets import default_grok
from trinity_cli.model import FAILED, OK, UNSUPPORTED, InstructionText
from trinity_cli.shown import Shown
from trinity_cli.state import Ledger
from trinity_cli.util import iso, now_utc

_LIMIT = 32000
_YES = {"y", "yes", "是"}


def _read(path: Path) -> tuple[str | None, str | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except FileNotFoundError:
        return None, "missing"
    except OSError as exc:
        return None, str(exc)


def _as_list(value: object) -> list[InstructionText]:
    if isinstance(value, InstructionText):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, InstructionText)]
    return []


def _confirmed(yes: bool, stdin) -> bool:
    if yes:
        return True
    if not getattr(stdin, "isatty", lambda: False)():
        return False
    try:
        return stdin.readline().strip().lower() in _YES
    except (OSError, ValueError):
        return False


def _draft(label: str, reason: str, text: str) -> str:
    return f"{label}：{reason}下面是可以自己貼上的草稿，沒有送出：\n---\n{text.rstrip()}\n---"


def _diff(current: str, wanted: str) -> str:
    if current.strip() == wanted.strip():
        return "相同"
    lines = list(
        difflib.unified_diff(current.splitlines(), wanted.splitlines(), fromfile="seat", tofile="brief.md", lineterm="")
    )
    return "\n".join(lines[:80]) if lines else "相同"


def _is_grok(seat) -> bool:
    return seat.key == "grok" or str(seat.key).startswith("grok-")


def _focus(seats, seat_name: str | None):
    if seat_name and seat_name != "grok":
        found = next((seat for seat in seats if seat.key == seat_name), None)
        if found is not None:
            return found
    return default_grok(seats)


def _target_for(seat, grok_bot: str | None) -> str | None:
    if not _is_grok(seat):
        return None
    return grok_bot or getattr(seat, "default_bot", None) or None


def run_show(path: Path) -> Shown:
    text, error = _read(path)
    if error == "missing":
        return Shown(0, f"還沒有 brief：{path}", {"path": str(path), "missing": True})
    if error:
        return Shown(1, f"讀不到 brief：{error}", {"path": str(path), "error": error})
    return Shown(0, f"{path}\n\n{text.rstrip()}", {"path": str(path), "text": text})


_TEMPLATE = """# brief

這份說明是你希望各座位記住的共同背景。
`brief push` 只在有指令 API 的座位寫入（目前是 Grok），而且會先問過你。
Your dot 和 Muse 沒有指令 API，push 只會印出草稿。

"""


def run_init(path: Path) -> Shown:
    if path.exists():
        return Shown(0, f"brief 已經存在，沒有覆寫：{path}", {"path": str(path), "created": False})
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_TEMPLATE, encoding="utf-8")
    except OSError as exc:
        return Shown(1, f"寫不了 brief：{exc}", {"path": str(path), "created": False, "error": str(exc)})
    return Shown(0, f"已建立 {path}", {"path": str(path), "created": True})


def run_diff(seats, path: Path, *, grok_bot: str | None = None, grok_seat: str | None = None) -> Shown:
    text, error = _read(path)
    if error == "missing":
        return Shown(
            0,
            f"還沒有 brief：{path}\n建立一份：`trinity-cli brief init`，或直接編輯這個檔案。",
            {"path": str(path), "missing": True},
        )
    if error:
        return Shown(1, f"讀不到 brief：{error}", {"path": str(path), "error": error})
    lines = [str(path), ""]
    rows = []
    failed = False
    focus = _focus(seats, grok_seat)
    for seat in seats:
        if _is_grok(seat) and seat is not focus:
            continue
        if seat.supports("memory"):
            result = call(seat, "memory")
            if result.state == OK and isinstance(result.value, str):
                lines.append(f"{seat.label} 記憶（只讀）：")
                lines.append(_diff(result.value, text))
                rows.append(
                    {
                        "seat": seat.key,
                        "state": "ok",
                        "memory": True,
                        "same": result.value.strip() == text.strip(),
                    }
                )
            elif result.state == FAILED:
                failed = True
                lines.append(f"{seat.label} 記憶：{result.error}" + (f" → {result.hint}" if result.hint else ""))
                rows.append({"seat": seat.key, "state": result.state, "memory": True, "error": result.error})
            else:
                lines.append(f"{seat.label} 記憶：{result.error or '不支援'}")
                rows.append({"seat": seat.key, "state": result.state, "memory": True, "error": result.error})
            lines.append("")
        target = _target_for(seat, grok_bot)
        if not seat.supports("instructions"):
            lines.append(f"{seat.label}：沒有指令 API，無法比對")
            rows.append({"seat": seat.key, "state": "unsupported", "error": "沒有指令 API"})
            continue
        result = call(seat, "instructions", target)
        if result.state != OK:
            if result.state != UNSUPPORTED:
                failed = True
            lines.append(f"{seat.label}：{result.error}")
            rows.append({"seat": seat.key, "state": result.state, "error": result.error})
            continue
        for item in _as_list(result.value):
            lines.append(f"{seat.label}/{item.target or seat.label}：")
            lines.append(_diff(item.text, text))
            rows.append({"seat": seat.key, "target": item.target, "state": "ok", "same": item.text.strip() == text.strip()})
        if not _as_list(result.value):
            lines.append(f"{seat.label}：讀不到目前的指令")
            rows.append({"seat": seat.key, "state": "ok", "same": False})
        lines.append("")
    return Shown(1 if failed else 0, "\n".join(lines).rstrip(), {"path": str(path), "seats": rows})


def run_push(
    seats,
    path: Path,
    *,
    yes: bool = False,
    grok_bot: str | None = None,
    grok_seat: str | None = None,
    ledger: Ledger | None = None,
    stdin=None,
    now=now_utc,
) -> Shown:
    text, error = _read(path)
    if error == "missing" or text is None:
        return Shown(2, f"還沒有 brief，沒有寫入：{path}", {"path": str(path), "updated": [], "sent": False})
    if error:
        return Shown(1, f"讀不到 brief：{error}", {"path": str(path), "updated": [], "sent": False})
    if not text.strip():
        return Shown(2, f"brief 是空的，沒有寫入：{path}", {"path": str(path), "updated": [], "sent": False})
    if len(text) > _LIMIT:
        return Shown(2, f"brief 超過 {_LIMIT} 字，沒有寫入。", {"path": str(path), "updated": [], "sent": False})
    drafts: list[str] = []
    writable: list[tuple] = []
    failures: list[str] = []
    focus = _focus(seats, grok_seat)
    for seat in seats:
        if _is_grok(seat) and seat is not focus:
            continue
        target = _target_for(seat, grok_bot)
        if not seat.supports("instructions"):
            drafts.append(_draft(seat.label, "沒有指令 API。", text))
            continue
        result = call(seat, "instructions", target)
        if result.state == UNSUPPORTED:
            drafts.append(_draft(seat.label, result.error + "。", text))
            continue
        if result.state != OK:
            failures.append(f"{seat.label}：{result.error}" + (f" → {result.hint}" if result.hint else ""))
            continue
        items = _as_list(result.value)
        writers = [item for item in items if item.writable]
        if not writers:
            drafts.append(_draft(seat.label, "讀得到指令，但不能寫回。", text))
            continue
        if len(writers) != 1:
            failures.append(f"{seat.label} 有多個 bot，沒有寫入。請用 --grok-bot 指定一個。")
            continue
        writable.append((seat, writers[0].target))
    blocks = list(drafts)
    if failures:
        blocks.extend(failures)
    if not writable:
        blocks.append("沒有可以寫入指令的座位，沒有送出。")
        return Shown(1 if failures else 0, "\n\n".join(blocks), {"path": str(path), "updated": [], "sent": False, "confirmed": False})
    names = "、".join(f"{seat.label}/{target}" for seat, target in writable)
    blocks.append(f"將寫入 {names} 的指令（只走該座位的指令 API，不會傳訊息）。")
    blocks.append(f"---\n{text.rstrip()}\n---")
    if not _confirmed(yes, stdin):
        blocks.append("沒有確認，沒有寫入。要寫入請加上 --yes。")
        return Shown(2, "\n\n".join(blocks), {"path": str(path), "updated": [], "sent": False, "confirmed": False})
    book = ledger or Ledger()
    updated = []
    failed = bool(failures)
    for seat, target in writable:
        book.append({"event": "brief_push", "seat": seat.key, "target": target, "status": "writing", "at": iso(now())})
        result = call(seat, "instructions", target, update=text)
        status = "updated" if result.state == OK else "failed"
        book.append(
            {
                "event": "brief_push",
                "seat": seat.key,
                "target": target,
                "status": status,
                "error": result.error,
                "at": iso(now()),
            }
        )
        if result.state == OK:
            updated.append({"seat": seat.key, "target": target})
            blocks.append(f"已寫入 {seat.label}/{target} 的指令。")
        else:
            failed = True
            blocks.append(f"✗ {seat.label}/{target} 沒有寫入：{result.error}" + (f" → {result.hint}" if result.hint else ""))
    blocks.append("沒有傳訊息給任何座位。")
    return Shown(1 if failed else 0, "\n\n".join(blocks), {"path": str(path), "updated": updated, "sent": False, "confirmed": True})
