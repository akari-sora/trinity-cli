"""Grok Bot, through `gbot --json`. Auth stays inside the Grok Bot app; trinity never sees it."""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from trinity_cli.config import clean_account, configured_gbot_account, configured_grok_bot
from trinity_cli.model import (
    Batch,
    InstructionText,
    Message,
    ReadOutcome,
    Result,
    SeatStatus,
    SendReceipt,
    SourceFailure,
    WaitOutcome,
)
from trinity_cli.redact import short_error
from trinity_cli.runner import Runner, env_with_tool_dir, find_tool
from trinity_cli.schedules import parse_schedules
from trinity_cli.seats.base import Problem, Seat
from trinity_cli.util import (
    WINDOW_CURSOR_ID,
    has_nonce,
    iso,
    local_stamp,
    now_utc,
    one_line,
    parse_time,
    with_nonce,
)

TRANSCRIPT_LIMIT = 40
FIRST_READ = 10
GBOT_FALLBACKS = ("~/.nvm/versions/node/*/bin/gbot", "/opt/homebrew/bin/gbot", "/usr/local/bin/gbot")
FIX_APP = "打開 Grok Bot app 確認已登入，再跑 `gbot doctor`"
FIX_INSTALL = "安裝 gbot（見 README）或設定 TRINITY_GBOT"
FIX_AMBIGUOUS = (
    "設定 TRINITY_GBOT_ACCOUNT（或 ~/.trinity-cli/config.json 的 gbot_account）。"
    "trinity 會在 gbot thread 的說明裡看到 --account 時帶上它，也會設 GBOT_ACCOUNT。"
    "打開 Grok Bot app 確認登入，用 `gbot accounts` 看標籤，再跑 `gbot doctor`"
)
_SCHEDULE_COMMANDS = ("schedules", "routines", "automations")
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
TIME_KEYS = ("createdAt", "created_at", "timestampMs", "timestamp", "time", "ts", "sentAt", "sent_at", "updatedAt", "updated_at")


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
    """user / assistant / unknown.

    `gbot --normalized` only keeps an explicit user/assistant role. Bot replies on
    this gateway are a following `{kind: "send-message", message: {type: "text"}}`
    entry, which that rule calls unknown. Approval cards use another message type
    and stay unknown so they are not treated as the reply.
    """
    nested = entry.get("message") if isinstance(entry.get("message"), dict) else {}
    if entry.get("kind") == "send-message" and nested.get("type") == "text":
        return "assistant"
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
    if isinstance(payload, dict) and "entryCount" in payload:
        return []
    raise Problem("gbot thread 的格式看不懂", "更新 gbot 後重試")


def instruction_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("description", "instructions"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


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
        account: str | None = None,
    ):
        self.runner = runner or Runner()
        self.binary = binary if binary is not None else find_tool("gbot", "TRINITY_GBOT", GBOT_FALLBACKS)
        self.default_bot = default_bot or configured_grok_bot()
        wanted = only_bots if only_bots is not None else os.environ.get("TRINITY_GROK_BOTS", "").split(",")
        self.only_bots = [name.strip() for name in wanted if name.strip()]
        self.account = configured_gbot_account() if account is None else clean_account(account)
        self.clock = clock
        self.sleep = sleep
        self.now = now
        self._help: str | None = None
        self._help_missing = False

    # --- plumbing -------------------------------------------------------

    def _child_env(self) -> dict:
        env = env_with_tool_dir(self.binary)
        if self.account:
            env = dict(env)
            env["GBOT_ACCOUNT"] = self.account
        return env

    def _run(self, *args: str, stdin: str | None = None, timeout: float = 45.0):
        if not self.binary:
            raise Problem("找不到 gbot", FIX_INSTALL)
        argv = [self.binary, "--json", *args]
        # --account is a subcommand option. Before the command name, gbot rejects it.
        if self.account and "--account" in self._help_text():
            argv += ["--account", self.account]
        return self.runner.run(argv, stdin=stdin, timeout=timeout, env=self._child_env())

    def _json(self, *args: str, timeout: float = 45.0) -> object:
        proc = self._run(*args, timeout=timeout)
        if proc.code != 0 or proc.timed_out:
            raise problem_from(proc)
        try:
            return json.loads(proc.out)
        except json.JSONDecodeError as exc:
            raise Problem(f"gbot {args[0]} 的輸出不是 JSON", "更新 gbot 後重試") from exc

    def _help_text(self) -> str:
        """Root help plus the subcommand helps that document --account and --after.

        `gbot --help` only lists command names. `--account` and `thread --after`
        appear on `gbot thread --help` and `gbot send --help`.
        """
        if self._help is None:
            if not self.binary:
                self._help = ""
                self._help_missing = True
            else:
                chunks: list[str] = []
                missing = False
                for extra in ((), ("thread",), ("bots",)):
                    proc = self.runner.run(
                        [self.binary, *extra, "--help"],
                        timeout=15,
                        env=env_with_tool_dir(self.binary),
                    )
                    if proc.code == 127:
                        missing = True
                        break
                    chunks.append(proc.out or "")
                    chunks.append(proc.err or "")
                self._help_missing = missing
                self._help = "" if missing else "\n".join(chunks)
        return self._help

    def _gbot_missing(self) -> Result | None:
        self._help_text()
        if not self.binary or self._help_missing:
            return Result.failed("找不到 gbot", FIX_INSTALL)
        return None

    def supports_after(self) -> bool:
        return "--after" in self._help_text()

    def login(self, *, mode: str = "token") -> Result:
        """Grok's credential stays in the app. trinity does not read it or start a login."""
        if mode != "token":
            return Result.failed("這個旗標只給 Muse", "`trinity-cli login muse --help`")
        return Result.failed(
            "Grok Bot 的登入在 Grok Bot app，trinity 不代登，也不讀 app 的登入",
            FIX_APP,
        )

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
            if not (isinstance(cursor, dict) and cursor.get("id")) and isinstance(cursors.get("*"), dict):
                cursor = cursors["*"]
            try:
                after = None
                if use_after and since is None and isinstance(cursor, dict):
                    found = cursor.get("id")
                    if isinstance(found, str) and found and found != WINDOW_CURSOR_ID:
                        after = found
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
                body = payload if isinstance(payload, dict) else {}
                gap = bool(body.get("gapReset"))
                new_id = body.get("cursor") if isinstance(body.get("cursor"), str) and body.get("cursor") else None
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

    # --- schedules / instructions ---------------------------------------

    def _schedule_command(self) -> str | None:
        text = self._help_text()
        for name in _SCHEDULE_COMMANDS:
            if name in text:
                return name
        return None

    def schedules(self) -> Result:
        missing = self._gbot_missing()
        if missing:
            return missing
        command = self._schedule_command()
        if command is None:
            return Result.unsupported("gbot 沒有排程指令")
        listed = f"{command} list" in self._help_text()
        try:
            payload = self._json(command, "list") if listed else self._json(command)
        except Problem as problem:
            return Result.failed(problem.error, problem.hint)
        return Result.ok(parse_schedules(payload))

    def _named_bots(self) -> list[tuple[str, str]]:
        bots = self._bots()
        return [(str(bot.get("name")), str(bot.get("id"))) for bot in bots if bot.get("name")]

    def _pick_bot(self, target: str | None) -> tuple[str, str]:
        target = target or self.default_bot
        pairs = self._named_bots()
        if target:
            for name, ref in pairs:
                if target in (name, ref):
                    return name, name
            return target, target
        if len(pairs) != 1:
            raise Problem(
                "Grok Bot 不只一個 bot，不知道要看哪一個",
                "用 --grok-bot、grok:<bot>，或設定 TRINITY_GROK_BOT",
            )
        return pairs[0][0], pairs[0][0]

    def _instruction_flags(self) -> tuple[bool, bool]:
        text = self._help_text()
        return ("bots get" in text, "bots update" in text and "--instructions" in text)

    def instructions(self, target: str | None = None, *, update: str | None = None) -> Result:
        missing = self._gbot_missing()
        if missing:
            if update is None:
                return missing
            return Result.failed(f"{missing.error}，沒有寫入", missing.hint)
        can_read, can_write = self._instruction_flags()
        if update is not None:
            if not can_write:
                return Result.unsupported("gbot 沒有 bots update --instructions")
            if update.startswith("-"):
                return Result.failed("指令內容以 - 開頭，gbot 會把它當成參數，沒有寫入", "在 brief 開頭加一行普通文字")
            try:
                name, ref = self._pick_bot(target)
            except Problem as problem:
                return Result.failed(f"{problem.error}，沒有寫入", problem.hint)
            try:
                proc = self._run("bots", "update", ref, "--instructions", update, timeout=60)
            except Problem as problem:
                return Result.failed(f"{problem.error}，沒有寫入", problem.hint)
            if proc.code != 0 or proc.timed_out:
                problem = problem_from(proc)
                return Result.failed(f"{problem.error}，沒有寫入", problem.hint)
            return Result.ok(InstructionText(name, update, True))
        if not can_read and not can_write:
            return Result.unsupported("gbot 沒有讀寫指令的指令")
        if not can_read:
            return Result.ok(InstructionText(target or self.default_bot or "", "", can_write))
        try:
            if target or self.default_bot:
                selected = [self._pick_bot(target)]
            else:
                selected = self._named_bots()
        except Problem as problem:
            return Result.failed(problem.error, problem.hint)
        texts: list[InstructionText] = []
        for name, ref in selected:
            try:
                payload = self._json("bots", "get", ref)
            except Problem as problem:
                return Result.failed(problem.error, problem.hint)
            texts.append(InstructionText(name, instruction_text(payload), can_write))
        if len(texts) == 1:
            return Result.ok(texts[0])
        return Result.ok(texts)

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
            delivery = payload.get("delivery") if isinstance(payload, dict) else None
            if delivery not in {"accepted", "unknown"}:
                delivery = "accepted"
            return Result.ok(SendReceipt(f"Grok Bot/{name or target}", str(ref or target), nonce, sent_at, delivery))
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
                    reply = next((m for m in messages[index + 1 :] if m.from_agent and m.text.strip()), None)
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
