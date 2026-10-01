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
import os
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
from trinity_cli.runner import LOGIN_TIMEOUT, Runner, find_tool
from trinity_cli.seats.base import Problem, Seat
from trinity_cli.util import WINDOW_CURSOR, WINDOW_CURSOR_ID, has_nonce, now_utc, one_line, with_nonce

FIX_INSTALL = "安裝 muse-web-cli，或用 TRINITY_MUSE_CLI 指定路徑"
FIX_MUSE = "安裝 Muse Code，或用 TRINITY_MUSE 指定路徑"
FIX_LOGIN = "muse-web-cli login"
FIX_START = "muse-web-cli start --headless"
FIX_TOKEN = (
    "執行 `trinity-cli login muse`（憑證留在 muse，不會寫入這個檔）。"
    "金鑰用 `trinity-cli login muse --api-key`。"
    "~/.trinity-cli/muse-credential 仍要自己放，權限 600。trinity 不讀、不複製"
)
def credential_mode_fix() -> str:
    if os.name == "nt":
        return (
            r'icacls "%USERPROFILE%\.trinity-cli\muse-credential" /inheritance:r /grant:r "%USERNAME%:R"'
        )
    return "chmod 600 ~/.trinity-cli/muse-credential"
_TOKEN_OK = (
    "Muse 登入已完成。憑證留在 muse 自己的設定裡，trinity 沒有讀取，"
    "也沒有寫入 ~/.trinity-cli/muse-credential。"
)
_KEY_OK = "已把標準輸入交給 muse auth set。trinity 沒有保存金鑰。"
_WEB_OK = "Muse 網頁已登入。接著可以執行 `muse-web-cli start --headless`。"
_WEB_WAIT = "請在開啟的 Chrome 視窗登入 Muse。這個工具不會輸入帳號密碼。"
FIRST_READ = 10
MESSAGE_LIMIT = 40
LIMIT_MAX = 100
CURSOR_KEY = "muse.messages"

_SETUP = {"browser_down", "session_expired", "region_blocked", "profile_busy", "credential_permissions"}
_PAGE = {"ui_changed", "timeout"}
_HINTS = {
    "session_expired": FIX_LOGIN,
    "browser_down": FIX_START,
    "credential_permissions": "credential file mode",
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
SIDE_CHAT = "目前在副聊天室"
SIDE_HINT = "在 Muse 視窗切回主聊天室後再讀、再送"
_CHAT_UNSUPPORTED = "chats 不支援，仍使用目前開啟的對話"
_CHAT_MISSING = "切換面板不在，仍使用目前開啟的對話"
_CHAT_UNCLEAR = "看不出目前是主聊天室還是副聊天室，仍使用目前開啟的對話"


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


def _hint(state: str, payload: dict) -> str:
    error = payload.get("error") if isinstance(payload.get("error"), str) else ""
    if state == "session_expired" and (payload.get("backend") == "api" or "muse-credential" in error):
        return FIX_TOKEN
    if state == "credential_permissions":
        return credential_mode_fix()
    hint = _HINTS.get(state) or ""
    if hint:
        return hint
    raw = payload.get("hint")
    return raw if isinstance(raw, str) else ""


def _content_key(role: str, text: str, seen: dict[str, int]) -> str:
    digest = hashlib.sha256(f"{role}\n{text}".encode()).hexdigest()[:12]
    seen[digest] = seen.get(digest, 0) + 1
    return f"{digest}.{seen[digest]}"


class MuseSeat(Seat):
    key = "muse"
    label = "Muse"
    unsupported_reason = "不支援"

    def __init__(
        self,
        runner: Runner | None = None,
        binary: str | None = None,
        *,
        clock=None,
        sleep=None,
        now=None,
        token_binary: str | None = None,
    ):
        self.runner = runner or Runner()
        if binary is None:
            self.binary = find_tool(
                "muse-web-cli",
                "TRINITY_MUSE_CLI",
                ("~/.local/bin/muse-web-cli", "~/.local/bin/muse-web-cli.exe"),
            )
        else:
            self.binary = binary or None
        if token_binary is None:
            self.token_binary = find_tool("muse", "TRINITY_MUSE", ("~/.local/bin/muse", "~/.local/bin/muse.exe"))
        else:
            self.token_binary = token_binary or None
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
        return Problem(error, _hint(state, payload))

    def _attach_muse(self, args: list[str], *, ok: str, bad: str) -> Result:
        """Public `muse` CLI. The child's output is not captured, so a token never lands here."""
        if not self.token_binary:
            return Result.failed("找不到 muse", FIX_MUSE)
        proc = self.runner.attach([self.token_binary, *args], timeout=LOGIN_TIMEOUT)
        if proc.code == 127:
            return Result.failed("找不到 muse", FIX_MUSE)
        if proc.timed_out:
            return Result.failed("Muse 登入逾時", "再執行一次 `trinity-cli login muse`")
        if proc.code != 0:
            return Result.failed(bad, FIX_TOKEN)
        return Result.ok(ok)

    def login(self, *, mode: str = "token") -> Result:
        """Token: `muse login` or `muse auth set`. Web seat: `muse-web-cli login`.

        trinity does not read ~/.config/muse/auth.json and does not copy a credential
        into ~/.trinity-cli/muse-credential.
        """
        if mode == "api-key":
            return self._attach_muse(
                ["auth", "set", "--provider", "meta", "--api-key-stdin"],
                ok=_KEY_OK,
                bad="Muse 金鑰沒有存進去",
            )
        if mode == "web":
            return self._web_login()
        if mode != "token":
            return Result.failed("看不懂的登入方式", "`trinity-cli login muse --help`")
        return self._attach_muse(["login"], ok=_TOKEN_OK, bad="Muse 登入沒有完成")

    def _web_login(self) -> Result:
        if not self.binary:
            return Result.failed("找不到 muse-web-cli", FIX_INSTALL)
        proc = self.runner.run([self.binary, "--json", "login"], timeout=LOGIN_TIMEOUT)
        if proc.code == 127:
            return Result.failed("找不到 muse-web-cli", FIX_INSTALL)
        payload = _object(proc.out)
        if proc.timed_out and not payload.get("state"):
            return Result.failed("Muse 網頁登入逾時", FIX_LOGIN)
        if not payload and proc.code == 0 and not proc.timed_out:
            return Result.failed("muse-web-cli login 的輸出不是 JSON", "更新 muse-web-cli 後重試")
        state = str(payload.get("state") or "")
        if payload.get("logged_in") is True and state in {"", "ok"} and proc.code == 0 and not proc.timed_out:
            return Result.ok(_WEB_OK)
        if state in {"", "ok"} and proc.code == 0 and not proc.timed_out:
            return Result.failed(_WEB_WAIT, FIX_LOGIN)
        problem = self._problem(proc, payload)
        return Result.failed(problem.error, problem.hint)

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

    def _chat(self) -> tuple[str, str]:
        """Current chat kind, without titles.

        `main` and `side` come from `chats`. `unknown` means trinity keeps the
        old behavior (whatever is open) and the note belongs on the status line.
        """
        proc, payload = self._run(["chats"], timeout=45)
        state = str(payload.get("state") or "")
        missing = [str(item) for item in payload.get("missing")] if isinstance(payload.get("missing"), list) else []
        if proc.code == 4 or state == "unsupported":
            return "unknown", _CHAT_UNSUPPORTED
        if "side_chats" in missing:
            return "unknown", _CHAT_MISSING
        if proc.timed_out or proc.code != 0 or state not in {"", "ok"}:
            raise self._problem(proc, payload)
        chats = payload.get("chats") if isinstance(payload.get("chats"), list) else []
        current = next((item for item in chats if isinstance(item, dict) and item.get("is_current") is True), None)
        kind = current.get("kind") if isinstance(current, dict) else None
        if kind == "side":
            return "side", ""
        if kind == "main":
            return "main", ""
        return "unknown", _CHAT_UNCLEAR

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
            kind, note = self._chat()
            hint = ""
            if kind == "main":
                parts.append("主聊天室")
            elif kind == "side":
                parts.append(SIDE_CHAT)
                problems.append(SIDE_CHAT)
                hint = SIDE_HINT
            else:
                parts.append(note)
            return Result.ok(
                SeatStatus(
                    " · ".join(parts),
                    waiting,
                    problems,
                    hint,
                    details={
                        "backend": payload.get("backend"),
                        "headless": payload.get("headless"),
                        "pending": count if isinstance(count, int) else 0,
                        "latest_assistant_is_card": bool(payload.get("latest_assistant_is_card")),
                        "chat": kind,
                    },
                )
            )

        return self._guard(run)

    def read(self, cursors: dict, *, since: datetime | None = None, limit: int = MESSAGE_LIMIT) -> Result:
        def run() -> Result:
            kind, _note = self._chat()
            if kind == "side":
                raise Problem(SIDE_CHAT, SIDE_HINT)
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
        try:
            kind, _note = self._chat()
        except Problem as problem:
            return Result.failed(f"{problem.error}，沒有送出", problem.hint)
        if kind == "side":
            return Result.failed(f"{SIDE_CHAT}，沒有送出", SIDE_HINT)
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
                if SIDE_CHAT in (result.error or ""):
                    return Result.failed(result.error, result.hint)
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
