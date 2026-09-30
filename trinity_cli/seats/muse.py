"""Muse through `muse-web-cli --json --autostart`.

Send does not pass `--wait`. muse-web-cli can wait inside one `send --wait`, but a
timeout there is harder to tell apart from "did it send", and the other seats
poll for the nonce themselves. trinity writes the ledger, calls `send` once
without `--wait`, then `wait` polls `messages`. A timeout never calls `send`
again.

Messages have no timestamps (only date separators). Times stay unknown. The
digest cursor is a content hash plus the occurrence of that text in the window.
If the previously seen tail is no longer in the window, the batch is marked so
digest can say 可能漏看.

`instructions` stays on the base class: Muse has no instruction API, so
`brief push` prints a draft. `memory` is read-only and only used by `brief diff`.
The api backend is a seam; when muse-web-cli reports it unsupported, so do we.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime

from trinity_cli.model import (
    Batch,
    Message,
    ReadOutcome,
    Result,
    ScheduleItem,
    SeatStatus,
    SendReceipt,
    WaitOutcome,
)
from trinity_cli.redact import short_error
from trinity_cli.runner import Runner, find_tool
from trinity_cli.seats.base import Problem, Seat
from trinity_cli.util import WINDOW_CURSOR, WINDOW_CURSOR_ID, has_nonce, now_utc, one_line, with_nonce

FIX_INSTALL = "安裝 muse-web-cli，或用 TRINITY_MUSE_CLI 指定路徑"
FIX_LOGIN = "muse-web-cli login"
FIX_START = "muse-web-cli start --headless"
FIRST_READ = 10
MESSAGE_LIMIT = 40
LIMIT_MAX = 100
CURSOR_KEY = "muse.messages"

_SETUP = {"browser_down", "session_expired", "region_blocked", "profile_busy", "credential_permissions"}
_PAGE = {"ui_changed", "timeout"}
_HINTS = {
    "session_expired": FIX_LOGIN,
    "browser_down": FIX_START,
}
_ERRORS = {
    "browser_down": "Muse 的瀏覽器沒有啟動",
    "session_expired": "Muse 登入工作階段已失效",
    "region_blocked": "Muse 在這個地區無法使用",
    "profile_busy": "Muse 的瀏覽器設定檔正在使用",
    "credential_permissions": "Muse 憑證檔權限不對",
    "ui_changed": "Muse 頁面結構對不上",
    "timeout": "Muse 頁面逾時",
}


class _Unsupported(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _object(text: str) -> dict:
    try:
        value = json.loads(text) if text.strip() else None
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _content_key(role: str, text: str, seen: dict[str, int]) -> str:
    digest = hashlib.sha256(f"{role}\n{text}".encode()).hexdigest()[:12]
    seen[digest] = seen.get(digest, 0) + 1
    return f"{digest}.{seen[digest]}"


class MuseSeat(Seat):
    key = "muse"
    label = "Muse"
    unsupported_reason = "不支援"

    def __init__(self, runner: Runner | None = None, binary: str | None = None, *, clock=None, sleep=None, now=None):
        self.runner = runner or Runner()
        if binary is None:
            self.binary = find_tool("muse-web-cli", "TRINITY_MUSE_CLI", ("~/.local/bin/muse-web-cli",))
        else:
            self.binary = binary or None
        self.clock = clock or time.monotonic
        self.sleep = sleep or time.sleep
        self.now = now or now_utc

    def _run(self, args: list[str], *, timeout: float):
        if not self.binary:
            raise Problem("找不到 muse-web-cli", FIX_INSTALL)
        proc = self.runner.run([self.binary, "--json", "--autostart", *args], timeout=timeout)
        if proc.code == 127:
            raise Problem("找不到 muse-web-cli", FIX_INSTALL)
        return proc, _object(proc.out)

    def _problem(self, proc, payload: dict) -> Problem:
        state = str(payload.get("state") or "")
        if proc.timed_out and not state:
            state = "timeout"
        if not state:
            if proc.code == 2:
                state = "browser_down"
            elif proc.code == 3:
                state = "ui_changed"
        error = payload.get("error") if isinstance(payload.get("error"), str) and payload.get("error") else ""
        if not error:
            error = _ERRORS.get(state) or short_error(proc.err) or "Muse 讀取失敗"
        hint = _HINTS.get(state) or ""
        if not hint and isinstance(payload.get("hint"), str):
            hint = payload["hint"]
        return Problem(error, hint)

    def _payload(self, args: list[str], *, timeout: float = 45.0) -> dict:
        proc, payload = self._run(args, timeout=timeout)
        state = str(payload.get("state") or "")
        if proc.code == 4 or state == "unsupported":
            reason = payload.get("error") if isinstance(payload.get("error"), str) and payload.get("error") else "不支援"
            raise _Unsupported(reason)
        if not payload and proc.code == 0 and not proc.timed_out:
            raise Problem("muse-web-cli 的輸出不是 JSON", "更新 muse-web-cli 後重試")
        if proc.timed_out or proc.code != 0 or state not in {"", "ok"}:
            raise self._problem(proc, payload)
        return payload

    def _guard(self, fn):
        try:
            return fn()
        except _Unsupported as exc:
            return Result.unsupported(exc.reason)
        except Problem as problem:
            return Result.failed(problem.error, problem.hint)

    def status(self) -> Result:
        def run() -> Result:
            payload = self._payload(["status"])
            waiting: list[str] = []
            problems: list[str] = []
            count = payload.get("pending")
            items: list[dict] = []
            if count is None or (isinstance(count, int) and not isinstance(count, bool) and count > 0):
                try:
                    pending = self._payload(["pending"])
                except _Unsupported:
                    pending = {}
                except Problem as problem:
                    problems.append(problem.error)
                    pending = {}
                raw_items = pending.get("items") if isinstance(pending.get("items"), list) else []
                items = [item for item in raw_items if isinstance(item, dict)]
                if not isinstance(count, int):
                    reported = pending.get("count")
                    count = reported if isinstance(reported, int) else len(items)
            if isinstance(count, int) and count > 0:
                if items:
                    for item in items:
                        title = one_line(str(item.get("title") or "待處理"), 80)
                        waiting.append(f"等你處理：{title}")
                else:
                    waiting.append(f"等你處理（{count}）")
            if payload.get("latest_assistant_is_card") is True:
                waiting.append("等你處理：最新回覆是卡片")
            parts = ["連線正常"]
            if payload.get("headless") is True:
                parts.append("背景")
            elif payload.get("headless") is False:
                parts.append("有視窗")
            backend = payload.get("backend")
            if isinstance(backend, str) and backend and backend != "browser":
                parts.append(backend)
            return Result.ok(
                SeatStatus(
                    " · ".join(parts),
                    waiting,
                    problems,
                    details={
                        "backend": payload.get("backend"),
                        "headless": payload.get("headless"),
                        "pending": count if isinstance(count, int) else 0,
                        "latest_assistant_is_card": bool(payload.get("latest_assistant_is_card")),
                    },
                )
            )

        return self._guard(run)

    def read(self, cursors: dict, *, since: datetime | None = None, limit: int = MESSAGE_LIMIT) -> Result:
        def run() -> Result:
            bounded = min(LIMIT_MAX, max(1, limit))
            payload = self._payload(["messages", "--limit", str(bounded)])
            raw = payload.get("messages") if isinstance(payload.get("messages"), list) else []
            rows = [item for item in raw if isinstance(item, dict) and item.get("role") in {"user", "assistant"}]
            counts: dict[str, int] = {}
            messages: list[Message] = []
            keys: list[str] = []
            for item in rows:
                role = str(item.get("role") or "")
                text = item.get("text") if isinstance(item.get("text"), str) else ""
                key = _content_key(role, text, counts)
                keys.append(key)
                messages.append(
                    Message(
                        source=self.label,
                        speaker="you" if role == "user" else self.label,
                        text=text,
                        at=None,
                        from_agent=role == "assistant",
                        key=key,
                    )
                )
            cursor = cursors.get(CURSOR_KEY) if isinstance(cursors, dict) else None
            if not (isinstance(cursor, dict) and cursor.get("id")) and isinstance(cursors, dict) and isinstance(cursors.get("*"), dict):
                cursor = cursors["*"]
            return Result.ok(ReadOutcome([_batch(messages, keys, cursor if isinstance(cursor, dict) else None, since)]))

        return self._guard(run)

    def send(self, target: str | None, text: str, nonce: str) -> Result:
        body = with_nonce(text, nonce)
        try:
            proc, payload = self._run(["send", "--", body], timeout=90)
        except Problem as problem:
            return Result.failed(f"{problem.error}，沒有送出", problem.hint)
        state = str(payload.get("state") or "")
        if proc.code == 4 or state == "unsupported":
            reason = payload.get("error") if isinstance(payload.get("error"), str) and payload.get("error") else "不支援"
            return Result.unsupported(reason)
        sent = bool(payload.get("sent"))
        attempted = bool(payload.get("attempted"))
        sent_at = self.now()
        label = target or self.label
        if proc.timed_out or (state == "timeout" and (attempted or sent)):
            error = payload.get("error") if isinstance(payload.get("error"), str) else ""
            return Result.ok(SendReceipt(label, label, nonce, sent_at, "accepted" if sent else "unknown", error=error or "送出逾時"))
        if sent and state in {"", "ok"} and proc.code == 0:
            return Result.ok(SendReceipt(label, label, nonce, sent_at, "accepted"))
        if not sent:
            problem = self._problem(proc, payload)
            return Result.failed(f"{problem.error}，沒有送出", problem.hint)
        error = payload.get("error") if isinstance(payload.get("error"), str) else ""
        return Result.ok(SendReceipt(label, label, nonce, sent_at, "accepted", error=error))

    def wait(self, receipt: SendReceipt, *, timeout: float, poll: float) -> Result:
        deadline = self.clock() + timeout
        polls = 0
        delivered: bool | None = None
        last_error = ""
        while True:
            polls += 1
            result = self.read({"*": dict(WINDOW_CURSOR)}, limit=MESSAGE_LIMIT)
            if result.state == "unsupported":
                return result
            if result.state != "ok":
                last_error = result.error
            else:
                outcome = result.value
                messages = outcome.batches[0].items if isinstance(outcome, ReadOutcome) and outcome.batches else []
                index = next((i for i, item in enumerate(messages) if not item.from_agent and has_nonce(item.text, receipt.nonce)), None)
                if index is not None:
                    delivered = True
                    reply = next((item for item in messages[index + 1 :] if item.from_agent), None)
                    if reply:
                        return Result.ok(WaitOutcome(True, reply, False, polls))
                elif delivered is None:
                    delivered = False
            if self.clock() >= deadline:
                return Result.ok(WaitOutcome(delivered, None, True, polls, last_error))
            self.sleep(min(poll, max(0.0, deadline - self.clock())))

    def schedules(self) -> Result:
        def run() -> Result:
            payload = self._payload(["upcoming"])
            groups = payload.get("groups") if isinstance(payload.get("groups"), list) else []
            items: list[ScheduleItem] = []
            for group in groups:
                if not isinstance(group, dict):
                    continue
                title = str(group.get("title") or "")
                rows = group.get("items") if isinstance(group.get("items"), list) else []
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    name = str(row.get("name") or row.get("title") or title or "未命名")
                    when = str(row.get("time") or "")
                    items.append(ScheduleItem(name, when, title))
            return Result.ok(items)

        return self._guard(run)

    def memory(self) -> Result:
        def run() -> Result:
            payload = self._payload(["memory"])
            text = payload.get("text") if isinstance(payload.get("text"), str) else ""
            return Result.ok(text)

        return self._guard(run)


def _batch(messages: list[Message], keys: list[str], cursor: dict | None, since: datetime | None) -> Batch:
    tail = keys[-1] if keys else None
    saved = {"id": tail, "keys": list(keys)} if tail else None
    if since is not None:
        return Batch(CURSOR_KEY, "Muse", messages, saved, False, "沒有時間戳，--since 無法過濾，顯示這次讀到的訊息")
    if isinstance(cursor, dict) and cursor.get("id") == WINDOW_CURSOR_ID:
        return Batch(CURSOR_KEY, "Muse", messages, saved, False, "")
    previous = cursor.get("id") if isinstance(cursor, dict) else None
    if not previous:
        shown = messages[-FIRST_READ:]
        note = f"第一次讀取：只顯示最近 {len(shown)} 則" if len(messages) > len(shown) else ""
        return Batch(CURSOR_KEY, "Muse", shown, saved, False, note)
    if previous in keys:
        return Batch(CURSOR_KEY, "Muse", messages[keys.index(previous) + 1 :], saved, False, "")
    seen = set(cursor.get("keys") or []) if isinstance(cursor, dict) else set()
    fresh = [item for item, key in zip(messages, keys) if key not in seen]
    return Batch(
        CURSOR_KEY,
        "Muse",
        fresh if fresh else messages,
        saved,
        True,
        "上次看到的結尾已經不在最近的訊息裡",
    )
