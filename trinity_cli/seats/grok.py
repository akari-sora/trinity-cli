"""Grok Bot, through `gbot --json`. Auth stays inside the Grok Bot app; trinity never sees it."""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from trinity_cli.model import Batch, Message, ReadOutcome, Result, SeatStatus, SendReceipt, SourceFailure, WaitOutcome
from trinity_cli.redact import short_error
from trinity_cli.runner import Runner, env_with_tool_dir, find_tool
from trinity_cli.seats.base import Problem, Seat
from trinity_cli.util import has_nonce, iso, local_stamp, now_utc, one_line, parse_time, with_nonce

TRANSCRIPT_LIMIT = 40
FIRST_READ = 10
GBOT_FALLBACKS = ("~/.nvm/versions/node/*/bin/gbot", "/opt/homebrew/bin/gbot", "/usr/local/bin/gbot")
FIX_APP = "打開 Grok Bot app 確認已登入，再跑 `gbot doctor`"
FIX_INSTALL = "安裝 gbot（見 README）或設定 TRINITY_GBOT"
FIX_AMBIGUOUS = "打開 Grok Bot app，只保留一個登入（登出多餘的帳號或工作區），再跑 `gbot doctor` 確認 session usable"
# gbot fails with these before any gateway request, so nothing was sent.
BEFORE_SEND = (
    "gateway descriptor",
    "safe storage",
    "no bot or group",
    "ambiguous name",
    "stdin message",
    "cursor_access_token",
    "ensuresandbox returned no",
)
TIME_KEYS = ("createdAt", "created_at", "timestamp", "time", "ts", "sentAt", "sent_at", "updatedAt", "updated_at")


def _text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(t for t in (_text(v) for v in value) if t)
    if isinstance(value, dict):
        if isinstance(value.get("text"), str) and value["text"]:
            return value["text"]
        if value.get("content") is not None:
            return _text(value["content"])
    return ""


def entry_text(entry: dict) -> str:
    for key in ("text", "prompt", "message", "preview", "content"):
        text = _text(entry.get(key))
        if text:
            return text
    return ""


def entry_role(entry: dict) -> str:
    """user / assistant / unknown, by the same explicit-role rule as `gbot --normalized`."""
    nested = entry.get("message") if isinstance(entry.get("message"), dict) else {}
    roles = {
        value
        for value in (nested.get("type"), nested.get("role"), entry.get("role"), entry.get("kind"), entry.get("type"))
        if value in ("user", "assistant")
    }
    return roles.pop() if len(roles) == 1 else "unknown"


def entry_id(entry: dict) -> str:
    for key in ("id", "messageId"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def entry_time(entry: dict) -> datetime | None:
    nested = entry.get("message") if isinstance(entry.get("message"), dict) else {}
    for source in (entry, nested):
        for key in TIME_KEYS:
            at = parse_time(source.get(key))
            if at:
                return at
    return None


def transcript_entries(payload: object) -> list[dict]:
    container = None
    if isinstance(payload, dict):
        container = payload.get("transcript", payload.get("thread"))
    if isinstance(container, list):
        return [e for e in container if isinstance(e, dict)]
    if isinstance(container, dict):
        for key in ("entries", "messages", "items"):
            if isinstance(container.get(key), list):
                return [e for e in container[key] if isinstance(e, dict)]
    raise Problem("gbot thread 的格式看不懂", "更新 gbot 後重試")


def to_message(entry: dict, bot_name: str) -> Message:
    role = entry_role(entry)
    speaker = bot_name if role == "assistant" else ("you" if role == "user" else "?")
    return Message(
        source=f"Grok Bot/{bot_name}",
        speaker=speaker,
        text=entry_text(entry),
        at=entry_time(entry),
        from_agent=role == "assistant",
        key=entry_id(entry),
    )


def transcript_delta(messages: list[Message], cursor: dict | None) -> tuple[list[Message], bool, dict | None, str]:
    """Same rule as upstream `gbot thread --after`: a cursor outside the window is a gap reset."""
    newest = next((m for m in reversed(messages) if m.key), None)
    new_cursor = {"id": newest.key} if newest else cursor
    if not cursor or not cursor.get("id"):
        shown = messages[-FIRST_READ:]
        note = f"第一次讀取：只顯示最近 {len(shown)} 則" if len(messages) > len(shown) else ""
        return shown, False, new_cursor, note
    keys = [m.key for m in messages]
    if cursor["id"] not in keys:
        return messages, True, new_cursor, f"上次讀到的位置已不在最近 {len(messages)} 則內"
    rest = messages[keys.index(cursor["id"]) + 1 :]
    if rest and not rest[-1].key:
        return messages, True, new_cursor, "最新一則沒有 id，無法接續"
    return rest, False, new_cursor, ""


class GrokSeat(Seat):
    key = "grok"
    label = "Grok Bot"

    def __init__(
        self,
        runner: Runner | None = None,
        binary: str | None = None,
        default_bot: str | None = None,
        only_bots: list[str] | None = None,
        clock=time.monotonic,
        sleep=time.sleep,
        now=now_utc,
    ):
        self.runner = runner or Runner()
        self.binary = binary if binary is not None else find_tool("gbot", "TRINITY_GBOT", GBOT_FALLBACKS)
        self.default_bot = default_bot or os.environ.get("TRINITY_GROK_BOT") or None
        wanted = only_bots if only_bots is not None else os.environ.get("TRINITY_GROK_BOTS", "").split(",")
        self.only_bots = [name.strip() for name in wanted if name.strip()]
        self.clock = clock
        self.sleep = sleep
        self.now = now
        self._after: bool | None = None

    # --- plumbing -------------------------------------------------------

    def _run(self, *args: str, stdin: str | None = None, timeout: float = 45.0):
        if not self.binary:
            raise Problem("找不到 gbot", FIX_INSTALL)
        argv = [self.binary, "--json", *args]
        return self.runner.run(argv, stdin=stdin, timeout=timeout, env=env_with_tool_dir(self.binary))

    def _json(self, *args: str, timeout: float = 45.0) -> object:
        proc = self._run(*args, timeout=timeout)
        if proc.code != 0 or proc.timed_out:
            raise problem_from(proc)
        try:
            return json.loads(proc.out)
        except json.JSONDecodeError as exc:
            raise Problem(f"gbot {args[0]} 的輸出不是 JSON", "更新 gbot 後重試") from exc

    def supports_after(self) -> bool:
        if self._after is None:
            if not self.binary:
                return False
            proc = self.runner.run([self.binary, "--help"], timeout=15, env=env_with_tool_dir(self.binary))
            self._after = "--after" in proc.out + proc.err
        return self._after

    def _doctor_problem(self) -> Problem | None:
        try:
            payload = self._json("doctor", timeout=20)
        except Problem:
            return None
        session = payload.get("grokBotAppSession") if isinstance(payload, dict) else None
        if not isinstance(session, dict) or session.get("usable"):
            return None
        if session.get("code") == "AMBIGUOUS_ENTRIES":
            return Problem("Grok Bot app 存了多個 gateway 登入，gbot 選不出要用哪一個", FIX_AMBIGUOUS)
        if not session.get("present"):
            return Problem("找不到 Grok Bot app 的登入", "安裝並打開 Grok Bot app 登入一次，再跑 `gbot doctor`")
        return Problem("Grok Bot app 的登入不能用", FIX_APP)

    def _bots(self) -> list[dict]:
        try:
            rows = self._json("bots", "list")
        except Problem as problem:
            raise self._doctor_problem() or problem
        if not isinstance(rows, list):
            raise Problem("gbot bots list 的格式看不懂", "更新 gbot 後重試")
        bots = [r for r in rows if isinstance(r, dict) and r.get("id") and r.get("kind", "bot") == "bot"]
        if self.only_bots:
            bots = [b for b in bots if b.get("name") in self.only_bots or b.get("id") in self.only_bots]
        return bots

    def _transcript(self, ref: str, limit: int, after: str | None = None) -> object:
        args = ["thread", ref, "--limit", str(limit)]
        if after:
            args += ["--after", after]
        return self._json(*args, timeout=45)

    # --- status ---------------------------------------------------------

    def status(self) -> Result:
        try:
            bots = self._bots()
        except Problem as problem:
            return Result.failed(problem.error, problem.hint)
        status = SeatStatus(summary="")
        if not bots:
            status.summary = "連線正常 · 沒有 bot"
            return Result.ok(status)

        def last_entry(bot: dict):
            try:
                entries = transcript_entries(self._transcript(bot["id"], 1))
                return (to_message(entries[-1], str(bot.get("name"))) if entries else None), None
            except Problem as problem:
                return None, problem

        with ThreadPoolExecutor(max_workers=min(4, len(bots))) as pool:
            lasts = list(pool.map(last_entry, bots))
        parts = ["連線正常"]
        rows = []
        for bot, (last, problem) in zip(bots, lasts):
            name = str(bot.get("name"))
            if problem:
                parts.append(f"{name} ✗")
                status.problems.append(f"{name}：{problem.error}")
                status.hint = status.hint or problem.hint
                continue
            if last is None:
                parts.append(f"{name} 沒有訊息")
                rows.append({"name": name, "last_message_at": None, "last_speaker": None})
                continue
            who = "bot" if last.from_agent else ("你" if last.speaker == "you" else "?")
            parts.append(f"{name} 最後訊息 {local_stamp(last.at)}（{who}）")
            rows.append({"name": name, "last_message_at": iso(last.at), "last_speaker": who})
            if last.from_agent:
                status.waiting.append(
                    f"Grok Bot/{name} 最後一句是 bot 說的（{local_stamp(last.at)}）：{one_line(last.text, 60)}"
                )
        status.summary = " · ".join(parts)
        status.details = {"bots": rows}
        return Result.ok(status)

    # --- read -----------------------------------------------------------

    def read(self, cursors: dict, *, since: datetime | None = None, limit: int = TRANSCRIPT_LIMIT) -> Result:
        try:
            bots = self._bots()
        except Problem as problem:
            return Result.failed(problem.error, problem.hint)
        limit = max(1, min(limit, 200))
        use_after = self.supports_after()
        outcome = ReadOutcome()

        def one(bot: dict):
            name = str(bot.get("name"))
            key = f"grok.{bot['id']}"
            label = f"Grok Bot/{name}"
            cursor = cursors.get(key)
            try:
                after = cursor.get("id") if (use_after and since is None and isinstance(cursor, dict)) else None
                payload = self._transcript(bot["id"], limit, after)
                messages = [to_message(e, name) for e in transcript_entries(payload)]
            except Problem as problem:
                return SourceFailure(label, problem.error, problem.hint)
            if since is not None:
                untimed = any(m.at is None for m in messages)
                new = [m for m in messages if m.at is None or m.at > since]
                newest = next((m for m in reversed(messages) if m.key), None)
                note = "這個來源沒有時間戳，--since 無法過濾，顯示整個視窗" if untimed and new else ""
                return Batch(key, label, new, {"id": newest.key} if newest else cursor, False, note)
            if after:
                gap = bool(payload.get("gapReset")) if isinstance(payload, dict) else False
                new_id = payload.get("cursor") if isinstance(payload, dict) else None
                note = f"gbot 回報 gapReset：上次位置不在最近 {limit} 則內" if gap else ""
                return Batch(key, label, messages, {"id": new_id or after}, gap, note)
            new, gap, new_cursor, note = transcript_delta(messages, cursor if isinstance(cursor, dict) else None)
            return Batch(key, label, new, new_cursor, gap, note)

        with ThreadPoolExecutor(max_workers=max(1, min(4, len(bots)))) as pool:
            for item in pool.map(one, bots):
                if isinstance(item, SourceFailure):
                    outcome.failures.append(item)
                else:
                    outcome.batches.append(item)
        return Result.ok(outcome)

    # --- send / wait ----------------------------------------------------

    def send(self, target: str | None, text: str, nonce: str) -> Result:
        target = target or self.default_bot
        if not target:
            try:
                bots = self._bots()
            except Problem as problem:
                return Result.failed(f"{problem.error}，沒有送出", problem.hint)
            if len(bots) != 1:
                return Result.failed(
                    "Grok Bot 不只一個 bot，不知道要問哪一個，沒有送出",
                    "用 `trinity-cli ask grok <bot> ...`、`--grok-bot NAME` 或設定 TRINITY_GROK_BOT",
                )
            target = str(bots[0].get("name"))
        sent_at = self.now()
        try:
            proc = self._run("send", target, "--stdin", stdin=with_nonce(text, nonce), timeout=60)
        except Problem as problem:
            return Result.failed(f"{problem.error}，沒有送出", problem.hint)
        if proc.code == 0 and not proc.timed_out:
            try:
                payload = json.loads(proc.out)
            except json.JSONDecodeError:
                payload = {}
            name = payload.get("name") if isinstance(payload, dict) else None
            ref = payload.get("id") if isinstance(payload, dict) else None
            return Result.ok(SendReceipt(f"Grok Bot/{name or target}", str(ref or target), nonce, sent_at, "accepted"))
        err = short_error(proc.err)
        if proc.code == 127 or (not proc.timed_out and any(mark in err.lower() for mark in BEFORE_SEND)):
            problem = problem_from(proc)
            return Result.failed(f"{problem.error}，沒有送出", problem.hint)
        error = "送出逾時" if proc.timed_out else err or f"exit {proc.code}"
        return Result.ok(SendReceipt(f"Grok Bot/{target}", target, nonce, sent_at, "unknown", error=error))

    def wait(self, receipt: SendReceipt, *, timeout: float, poll: float) -> Result:
        deadline = self.clock() + timeout
        polls = 0
        delivered: bool | None = None
        last_error = ""
        name = receipt.target.split("/", 1)[-1]
        while True:
            polls += 1
            try:
                entries = transcript_entries(self._transcript(receipt.target_ref, TRANSCRIPT_LIMIT))
                messages = [to_message(e, name) for e in entries]
                index = next(
                    (i for i, m in enumerate(messages) if not m.from_agent and has_nonce(m.text, receipt.nonce)),
                    None,
                )
                if index is not None:
                    delivered = True
                    reply = next((m for m in messages[index + 1 :] if m.from_agent), None)
                    if reply:
                        return Result.ok(WaitOutcome(True, reply, False, polls))
                elif delivered is None:
                    delivered = False
            except Problem as problem:
                last_error = problem.error
            remaining = deadline - self.clock()
            if remaining <= 0:
                return Result.ok(WaitOutcome(delivered, None, True, polls, last_error))
            self.sleep(min(poll, remaining))


def problem_from(proc) -> Problem:
    err = short_error(proc.err)
    low = err.lower()
    if proc.code == 127:
        return Problem("找不到 gbot", FIX_INSTALL)
    if proc.timed_out or "timed out" in low:
        return Problem("Grok Bot gateway 逾時", "確認網路與 Grok Bot app，再跑 `gbot doctor`")
    if "multiple saved gateway entries" in low:
        return Problem("Grok Bot app 存了多個 gateway 登入，gbot 選不出要用哪一個", FIX_AMBIGUOUS)
    if any(mark in low for mark in ("gateway descriptor", "safe storage", "cursor_access_token", "ensuresandbox")):
        return Problem("讀不到 Grok Bot app 的登入", FIX_APP)
    if any(mark in low for mark in ("401", "403", "unauthorized", "forbidden")):
        return Problem("Grok Bot 登入失效", "打開 Grok Bot app 重新登入，再跑 `gbot doctor`")
    if "no bot or group" in low or "ambiguous name" in low:
        return Problem(f"gbot 找不到這個 bot：{err}", "用 `gbot bots list` 看名字")
    return Problem(f"gbot 失敗：{err or f'exit {proc.code}'}", FIX_APP)
