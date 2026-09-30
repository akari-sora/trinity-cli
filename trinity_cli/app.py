"""status / digest / ask on top of any list of seats."""

from __future__ import annotations

import shutil
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

from trinity_cli.model import FAILED, OK, UNSUPPORTED, Message, ReadOutcome, Result, SeatStatus, WaitOutcome
from trinity_cli.redact import scrub_ids
from trinity_cli.seats.base import Seat
from trinity_cli.state import Ledger
from trinity_cli.util import iso, local_stamp, now_utc, one_line

NOT_EMPTY = "（這不代表沒有新訊息）"


def call(seat: Seat, capability: str, *args, **kwargs) -> Result:
    """Run one capability. An adapter bug becomes that seat's failure, never the whole command's."""
    try:
        result = getattr(seat, capability)(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        detail = scrub_ids(f"{type(exc).__name__}: {exc}")
        return Result.failed(f"{seat.label} {capability} 內部錯誤：{detail}", "請回報這個錯誤")
    if not isinstance(result, Result):
        return Result.failed(f"{seat.label} {capability} 回傳格式不對", "請回報這個錯誤")
    return result


def each(seats: list, fn) -> list:
    if not seats:
        return []
    with ThreadPoolExecutor(max_workers=len(seats)) as pool:
        return list(pool.map(fn, seats))


# --- status -----------------------------------------------------------------


def collect_status(seats: list[Seat]) -> list[tuple[Seat, Result]]:
    return list(zip(seats, each(seats, lambda seat: call(seat, "status"))))


def status_exit(reports: list[tuple[Seat, Result]]) -> int:
    return 1 if any(r.state == FAILED for _, r in reports) else 0


def render_status(reports: list[tuple[Seat, Result]]) -> str:
    lines: list[str] = []
    waiting = [item for _, r in reports if r.state == OK and isinstance(r.value, SeatStatus) for item in r.value.waiting]
    if waiting:
        lines.append("等你處理：")
        lines.extend(f"  • {item}" for item in waiting)
        lines.append("")
    width = max(len(seat.label) for seat, _ in reports) if reports else 0
    for seat, r in reports:
        label = seat.label.ljust(width)
        if r.state == OK:
            s: SeatStatus = r.value
            mark = "⚠" if s.problems else "✓"
            line = f"{label}  {mark} {s.summary}"
            if s.problems:
                line += " · 問題：" + "；".join(s.problems)
                if s.hint:
                    line += f" → {s.hint}"
        elif r.state == FAILED:
            line = f"{label}  ✗ 失敗：{r.error}" + (f" → {r.hint}" if r.hint else "")
        else:
            line = f"{label}  – {r.error}"
        lines.append(line)
    return "\n".join(lines)


def status_json(reports: list[tuple[Seat, Result]]) -> dict:
    seats = []
    for seat, r in reports:
        row = {"seat": seat.key, "label": seat.label, "state": r.state}
        if r.state == OK:
            s: SeatStatus = r.value
            row.update(summary=s.summary, waiting=s.waiting, problems=s.problems, hint=s.hint, details=s.details)
        else:
            row.update(error=r.error, hint=r.hint)
        seats.append(row)
    waiting = [w for row in seats for w in row.get("waiting", [])]
    return {"waiting": waiting, "seats": seats}


# --- digest -----------------------------------------------------------------


@dataclass
class DigestView:
    text: str
    data: dict
    cursor_updates: dict = field(default_factory=dict)
    failed: bool = False


def collect_digest(seats: list[Seat], cursors: dict, since: datetime | None, limits: dict) -> list[tuple[Seat, Result]]:
    def read(seat: Seat) -> Result:
        kwargs = {"since": since}
        if seat.key in limits:
            kwargs["limit"] = limits[seat.key]
        return call(seat, "read", cursors, **kwargs)

    return list(zip(seats, each(seats, read)))


def build_digest(reports: list[tuple[Seat, Result]], *, advance: bool) -> DigestView:
    header: list[str] = []
    data: dict = {"items": [], "gaps": [], "failures": [], "unsupported": [], "notes": []}
    timeline: list[tuple[tuple, str, dict | None]] = []
    updates: dict = {}
    failed = False
    order = 0
    for seat, r in reports:
        if r.state == UNSUPPORTED:
            header.append(f"– {seat.label}：{r.error}")
            data["unsupported"].append({"seat": seat.key, "label": seat.label, "reason": r.error})
            continue
        if r.state == FAILED:
            failed = True
            header.append(f"✗ {seat.label} 讀取失敗：{r.error}" + (f" → {r.hint}" if r.hint else "") + NOT_EMPTY)
            data["failures"].append({"source": seat.label, "error": r.error, "hint": r.hint})
            continue
        outcome: ReadOutcome = r.value
        for failure in outcome.failures:
            failed = True
            header.append(f"✗ {failure.label} 讀取失敗：{failure.error}" + (f" → {failure.hint}" if failure.hint else "") + NOT_EMPTY)
            data["failures"].append({"source": failure.label, "error": failure.error, "hint": failure.hint})
        for batch in outcome.batches:
            order += 1
            if batch.new_cursor:
                updates[batch.cursor_key] = batch.new_cursor
            if batch.note and not batch.gap:
                header.append(f"ℹ {batch.label}：{batch.note}")
                data["notes"].append({"source": batch.label, "note": batch.note})
            if batch.gap:
                data["gaps"].append({"source": batch.label, "note": batch.note})
                first = batch.items[0] if batch.items else None
                key = _sort_key(first, order, -1)
                timeline.append((key, f"── {batch.label}：這之前可能漏看（{batch.note}）──", None))
            for position, message in enumerate(batch.items):
                timeline.append((_sort_key(message, order, position), _line(message), _item(message, batch.gap and position == 0)))
    timeline.sort(key=lambda row: row[0])
    lines = list(header)
    if header and timeline:
        lines.append("")
    lines.extend(row[1] for row in timeline)
    data["items"] = [row[2] for row in timeline if row[2] is not None]
    count = len(data["items"])
    if count == 0 and not failed:
        lines.append("沒有新訊息。")
    elif count == 0:
        lines.append("其他來源沒有新訊息；失敗的來源請看上面。")
    else:
        lines.append("")
        lines.append(f"共 {count} 則新訊息。" + ("" if advance else "（沒有更新讀取位置）"))
    data["advanced"] = advance
    return DigestView("\n".join(lines), data, updates if advance else {}, failed)


def _sort_key(message: Message | None, order: int, position: int) -> tuple:
    if message is not None and message.at is not None:
        return (0, message.at.timestamp(), order, position)
    return (1, 0.0, order, position)


def _line(message: Message) -> str:
    stamp = _pad(local_stamp(message.at), 11)
    return f"{stamp}  {message.source}  {message.speaker}: {one_line(message.text, 400)}"


def _item(message: Message, gap_before: bool) -> dict:
    return {
        "at": iso(message.at),
        "source": message.source,
        "speaker": message.speaker,
        "from_agent": message.from_agent,
        "text": message.text,
        "gap_before": gap_before,
    }


# --- ask --------------------------------------------------------------------


@dataclass
class AskRow:
    seat: Seat
    target: str
    state: str
    send: str = ""
    readback: str = ""
    reply: Message | None = None
    error: str = ""
    hint: str = ""


def ask_one(
    seat: Seat,
    target: str | None,
    text: str,
    nonce: str,
    *,
    ask_id: str,
    ledger: Ledger,
    timeout: float,
    poll: float,
    now=now_utc,
) -> AskRow:
    label = seat.label if target is None else f"{seat.label}/{target}"
    if not seat.supports("send"):
        reason = call(seat, "send", target, text, nonce)
        return AskRow(seat, label, UNSUPPORTED, error=reason.error or seat.unsupported_reason)
    base = {"ask_id": ask_id, "seat": seat.key, "target": label, "nonce": nonce}
    ledger.append({**base, "event": "sending", "at": iso(now())})
    sent = call(seat, "send", target, text, nonce)
    if sent.state == UNSUPPORTED:
        ledger.append({**base, "event": "unsupported", "error": sent.error, "at": iso(now())})
        return AskRow(seat, label, UNSUPPORTED, error=sent.error)
    if sent.state != OK:
        ledger.append({**base, "event": "not_sent", "error": sent.error, "at": iso(now())})
        return AskRow(seat, label, FAILED, send="not_sent", error=sent.error, hint=sent.hint)
    receipt = sent.value
    base["target"] = receipt.target
    ledger.append({**base, "event": "sent", "sent_at": iso(receipt.sent_at), "delivery": receipt.delivery, "error": receipt.error})
    waited = call(seat, "wait", receipt, timeout=timeout, poll=poll)
    if waited.state != OK:
        ledger.append({**base, "event": "result", "sent_at": iso(receipt.sent_at), "delivery": receipt.delivery,
                       "readback": "unknown", "reply": "error", "error": waited.error, "at": iso(now())})
        return AskRow(seat, receipt.target, FAILED, send=receipt.delivery, readback="unknown", error=waited.error, hint=waited.hint)
    outcome: WaitOutcome = waited.value
    readback = {True: "confirmed", False: "not_seen", None: "unknown"}[outcome.delivered]
    ledger.append({
        **base,
        "event": "result",
        "sent_at": iso(receipt.sent_at),
        "delivery": receipt.delivery,
        "readback": readback,
        "reply": "replied" if outcome.reply else "timed_out",
        "replied_at": iso(outcome.reply.at) if outcome.reply else None,
        "polls": outcome.polls,
        "at": iso(now()),
    })
    state = "replied" if outcome.reply else "timed_out"
    return AskRow(seat, receipt.target, state, send=receipt.delivery, readback=readback, reply=outcome.reply,
                  error=outcome.error or receipt.error)


def run_ask(pairs: list[tuple[Seat, str | None]], text: str, nonce: str, **kwargs) -> list[AskRow]:
    if not pairs:
        return []
    with ThreadPoolExecutor(max_workers=len(pairs)) as pool:
        return list(pool.map(lambda pair: ask_one(pair[0], pair[1], text, nonce, **kwargs), pairs))


def ask_exit(rows: list[AskRow]) -> int:
    return 0 if all(row.state in ("replied", UNSUPPORTED) for row in rows) else 1


def _row_lines(row: AskRow, timeout: float) -> list[str]:
    readback = {
        "confirmed": "送達：讀回確認",
        "not_seen": "送達：沒讀回到（沒有重送）",
        "unknown": "送達：無法讀回（沒有重送）",
    }.get(row.readback, "")
    if row.state == UNSUPPORTED:
        return [f"– {row.error}"]
    if row.state == FAILED:
        lines = [f"✗ {row.error}"] + ([f"→ {row.hint}"] if row.hint else [])
        return lines + ([readback] if readback else [])
    if row.state == "timed_out":
        lines = [f"⏱ 等了 {timeout:.0f} 秒沒有回覆，沒有重送"]
        if row.send == "unknown":
            lines.append(f"送出狀態不明：{row.error}")
        return lines + [readback]
    lines = [f"✓ {local_stamp(row.reply.at)} {row.reply.speaker} 回覆", readback, ""]
    lines.extend(row.reply.text.strip().splitlines() or [""])
    return lines


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _wrap(line: str, width: int) -> list[str]:
    out, current, used = [], "", 0
    for ch in line:
        w = _width(ch)
        if used + w > width:
            out.append(current)
            current, used = "", 0
        current += ch
        used += w
    out.append(current)
    return out


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


def render_ask(rows: list[AskRow], *, nonce: str, timeout: float, ledger_path: str, columns: int | None = None) -> str:
    columns = columns or shutil.get_terminal_size((120, 24)).columns
    blocks = [(row.target, _row_lines(row, timeout)) for row in rows]
    footer = f"nonce {nonce} · 送出紀錄：{ledger_path}"
    count = len(blocks)
    col = (columns - 3 * (count - 1)) // count if count else columns
    if count <= 1 or col < 24:
        out: list[str] = []
        for title, lines in blocks:
            out.append(f"== {title} ==")
            out.extend(lines)
            out.append("")
        return "\n".join(out + [footer])
    wrapped = []
    for title, lines in blocks:
        cells = _wrap(title, col) + ["─" * col]
        for line in lines:
            cells.extend(_wrap(line, col))
        wrapped.append(cells)
    height = max(len(cells) for cells in wrapped)
    out = []
    for i in range(height):
        out.append(" │ ".join(_pad(cells[i] if i < len(cells) else "", col) for cells in wrapped).rstrip())
    return "\n".join(out + ["", footer])


def ask_json(rows: list[AskRow], *, ask_id: str, nonce: str) -> dict:
    return {
        "ask_id": ask_id,
        "nonce": nonce,
        "results": [
            {
                "seat": row.seat.key,
                "target": row.target,
                "state": row.state,
                "send": row.send,
                "readback": row.readback,
                "reply": None
                if row.reply is None
                else {"at": iso(row.reply.at), "speaker": row.reply.speaker, "text": row.reply.text},
                "error": row.error,
                "hint": row.hint,
            }
            for row in rows
        ],
    }
