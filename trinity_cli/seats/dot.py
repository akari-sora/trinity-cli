"""Your dot, through `chatgpt-dot-cli --json`. trinity never opens ~/.codex/auth.json."""

from __future__ import annotations

import json
import os
import platform
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from trinity_cli.model import Batch, Message, ReadOutcome, Result, SeatStatus, SendReceipt, SourceFailure, WaitOutcome
from trinity_cli.schedules import parse_schedules
from trinity_cli.redact import short_error
from trinity_cli.runner import Runner, find_tool
from trinity_cli.seats.base import Problem, Seat
from trinity_cli.util import has_nonce, iso, local_stamp, now_utc, one_line, parse_time, with_nonce

# chatgpt-dot-cli v0.2.1 rejects --limit outside 1..32 with exit 2 and sends no request.
MESSAGE_LIMIT = 30
MESSAGE_LIMIT_MAX = 32
FIRST_READ = 10
PER_DOT = {"messages", "computers", "env", "activity", "send", "automations"}
FIX_LOGIN = "執行 `codex login` 後重試"
FIX_INSTALL = "安裝 chatgpt-dot-cli（見 README）或設定 TRINITY_DOT_CLI"
FIX_NETWORK = "檢查網路後重跑；單獨測試：`chatgpt-dot-cli list`"


def dot_name(dot: dict) -> str:
    name = dot.get("display_name")
    return name.strip() if isinstance(name, str) and name.strip() else "Your dot"


def dot_sender_ids(dot: dict) -> set[str]:
    """Same rule as chatgpt-dot-cli's text view: only the dot's room member has aeon_id."""
    preview = dot.get("messaging_room_preview")
    members = preview.get("members") if isinstance(preview, dict) else None
    return {
        m["account_user_id"]
        for m in members or []
        if isinstance(m, dict) and m.get("aeon_id") and isinstance(m.get("account_user_id"), str)
    }


def _host_key(name: str) -> str:
    name = name.strip().lower().replace(" ", "-")
    return name[: -len(".local")] if name.endswith(".local") else name


def this_mac_names() -> set[str]:
    return {_host_key(n) for n in (socket.gethostname(), platform.node()) if n}


def _body(payload: object) -> dict:
    if isinstance(payload, dict) and isinstance(payload.get("body"), dict):
        return payload["body"]
    return {}


def _duration(seconds: object) -> str:
    if not isinstance(seconds, (int, float)) or seconds < 0:
        return "?"
    if seconds >= 86400:
        return f"{seconds / 86400:.1f} 天"
    if seconds >= 3600:
        return f"{seconds / 3600:.1f} 小時"
    return f"{max(1, round(seconds / 60))} 分鐘"


class DotSeat(Seat):
    key = "dot"
    label = "Your dot"

    def __init__(
        self,
        runner: Runner | None = None,
        binary: str | None = None,
        dot_id: str | None = None,
        hostnames: set[str] | None = None,
        include_activity: bool = True,
        clock=time.monotonic,
        sleep=time.sleep,
        now=now_utc,
    ):
        self.runner = runner or Runner()
        self.binary = binary if binary is not None else find_tool(
            "chatgpt-dot-cli", "TRINITY_DOT_CLI", ("~/.local/bin/chatgpt-dot-cli",)
        )
        self.dot_id = dot_id if dot_id is not None else os.environ.get("TRINITY_DOT_ID") or None
        self.hostnames = hostnames if hostnames is not None else this_mac_names()
        self.include_activity = include_activity
        self.clock = clock
        self.sleep = sleep
        self.now = now

    # --- plumbing -------------------------------------------------------

    def _cli(self, command: str, *args: str, timeout: float = 60.0) -> object:
        if not self.binary:
            raise Problem("找不到 chatgpt-dot-cli", FIX_INSTALL)
        argv = [self.binary, "--json", command, *args]
        if self.dot_id and command in PER_DOT:
            argv += ["--dot-id", self.dot_id]
        proc = self.runner.run(argv, timeout=timeout)
        if proc.timed_out:
            raise Problem(f"chatgpt-dot-cli {command} 逾時", "網路或 ChatGPT 服務慢；稍後重跑")
        if proc.code == 127:
            raise Problem("找不到 chatgpt-dot-cli", FIX_INSTALL)
        if proc.code == 2:
            err = short_error(proc.err)
            low = err.lower()
            if any(mark in low for mark in ("auth file", "chatgpt login", "access token", "account id", "login expired", "401")):
                raise Problem("ChatGPT 登入檔不能用（不存在或不是 ChatGPT 登入）", FIX_LOGIN)
            raise Problem(f"chatgpt-dot-cli {command} 用法錯誤：{err or 'exit 2'}", "檢查參數；`--limit` 只能是 1 到 32，dot id 用 `--dot-id`")
        if proc.code != 0:
            err = short_error(proc.err)
            if "401" in err or "login expired" in err.lower():
                raise Problem("ChatGPT 登入過期（401）", FIX_LOGIN)
            raise Problem(f"chatgpt-dot-cli {command} 失敗：{err or f'exit {proc.code}'}", FIX_NETWORK)
        try:
            return json.loads(proc.out)
        except json.JSONDecodeError as exc:
            raise Problem(f"chatgpt-dot-cli {command} 的輸出不是 JSON", "更新 chatgpt-dot-cli") from exc

    def _try(self, command: str, *args: str, timeout: float = 60.0) -> tuple[object, Problem | None]:
        try:
            return self._cli(command, *args, timeout=timeout), None
        except Problem as problem:
            return None, problem

    def _pick(self, dots: object) -> dict:
        if not isinstance(dots, list):
            raise Problem("chatgpt-dot-cli list 的格式看不懂", "更新 chatgpt-dot-cli")
        dots = [d for d in dots if isinstance(d, dict)]
        if self.dot_id:
            for dot in dots:
                if dot.get("id") == self.dot_id:
                    return dot
            raise Problem("找不到 TRINITY_DOT_ID 指定的 dot", "用 `chatgpt-dot-cli list` 確認 id")
        if not dots:
            raise Problem("這個 ChatGPT 帳號沒有 dot", "先在 ChatGPT app 建立 Your dot")
        if len(dots) > 1:
            raise Problem("帳號有多個 dot，trinity 不知道要看哪一個", "設定 TRINITY_DOT_ID（id 從 `chatgpt-dot-cli list` 拿）")
        return dots[0]

    def _messages(self, raw: object, dot: dict) -> list[Message]:
        # v0.2.1 --json is always {"name","lines","messages"} (oldest first).
        # Extra keys, including "note" on an empty room, are ignored. A bare list
        # is still accepted so a partial payload does not get misread as a speaker.
        if isinstance(raw, dict) and isinstance(raw.get("messages"), list):
            raw = raw["messages"]
        if not isinstance(raw, list):
            raise Problem("chatgpt-dot-cli messages 的格式看不懂", "更新 chatgpt-dot-cli")
        dot_ids = dot_sender_ids(dot)
        if raw and not dot_ids:
            raise Problem(
                "無法從 JSON 判斷 dot 訊息是誰說的（房間成員裡沒有帶 aeon_id 的 dot）",
                "chatgpt-dot-cli 的 JSON 可能改了；trinity 不猜發話者，請回報",
            )
        name = dot_name(dot)
        out = []
        for item in raw:
            if not isinstance(item, dict) or item.get("deleted_at"):
                continue
            content = item.get("content") if isinstance(item.get("content"), dict) else {}
            text = content.get("text") if isinstance(content.get("text"), str) else item.get("preview") or ""
            from_dot = item.get("account_user_id") in dot_ids
            out.append(
                Message(
                    source=name,
                    speaker="dot" if from_dot else "you",
                    text=str(text),
                    at=parse_time(item.get("created_at")),
                    from_agent=from_dot,
                    key=str(item.get("id") or ""),
                )
            )
        out.sort(key=lambda m: m.at.timestamp() if m.at else 0.0)
        return out

    # --- status ---------------------------------------------------------

    def status(self) -> Result:
        with ThreadPoolExecutor(max_workers=5) as pool:
            jobs = {
                "list": pool.submit(self._try, "list", timeout=45),
                "usage": pool.submit(self._try, "usage", timeout=45),
                "computers": pool.submit(self._try, "computers", timeout=45),
                "env": pool.submit(self._try, "env", timeout=45),
                "last": pool.submit(self._try, "messages", "--limit", "1", timeout=45),
            }
            got = {name: job.result() for name, job in jobs.items()}
        dots, problem = got["list"]
        if problem:
            return Result.failed(problem.error, problem.hint)
        try:
            dot = self._pick(dots)
        except Problem as problem:
            return Result.failed(problem.error, problem.hint)

        name = dot_name(dot)
        status = SeatStatus(summary="")
        parts: list[str] = []
        details: dict = {"name": name, "paused": bool(dot.get("is_paused")), "status": dot.get("status")}

        def note(problem: Problem, what: str) -> None:
            parts.append(f"{what} ✗")
            status.problems.append(problem.error)
            status.hint = status.hint or problem.hint

        if dot.get("is_paused"):
            parts.append("已暫停")
            status.waiting.append(f"{name} 已暫停（要恢復請到 ChatGPT app）")
        elif dot.get("status") == "active":
            parts.append("運作中")
        else:
            parts.append(f"狀態 {dot.get('status')}")

        payload, problem = got["computers"]
        if problem:
            note(problem, "電腦")
        else:
            body = _body(payload)
            computers = [c for c in body.get("computers") or [] if isinstance(c, dict)]
            mine = [c for c in computers if _host_key(str(c.get("display_name") or "")) in self.hostnames]
            attached = any(c.get("is_attached") for c in mine)
            if mine:
                parts.append("這台 Mac 已連接" if attached else "這台 Mac 沒連接")
            else:
                parts.append("沒看到這台 Mac")
            user_machines = [c for c in computers if c.get("kind") == "user"]
            linked = sum(1 for c in user_machines if c.get("is_attached"))
            parts.append(f"電腦 {linked}/{len(user_machines)} 已連接")
            if body.get("local_computer_access_disabled_by_admin"):
                parts.append("本機電腦存取被管理員關閉")
            details.update(this_mac_attached=attached if mine else None, computers_attached=linked, computers=len(user_machines))

        payload, problem = got["env"]
        if problem:
            note(problem, "環境")
        else:
            body = _body(payload)
            env_state = body.get("status")
            not_ready = [
                f"{c.get('type')} {c.get('status')}"
                for c in body.get("capabilities") or []
                if isinstance(c, dict) and c.get("status") not in ("ready", None)
            ]
            parts.append(f"環境 {env_state}" + (f"（{'、'.join(not_ready)}）" if not_ready else ""))
            details["environment"] = env_state

        payload, problem = got["usage"]
        if problem:
            note(problem, "額度")
        else:
            body = _body(payload)
            limits = body.get("rate_limit") if isinstance(body.get("rate_limit"), dict) else {}
            window = limits.get("primary_window") if isinstance(limits.get("primary_window"), dict) else {}
            used = window.get("used_percent")
            reset = _duration(window.get("reset_after_seconds"))
            if used is not None:
                parts.append(f"額度已用 {used}%（{reset}後重置）")
            if limits.get("limit_reached") or limits.get("allowed") is False:
                status.waiting.append(f"{name} 額度用完了（{reset}後重置）")
            details.update(plan=body.get("plan_type"), quota_used_percent=used, quota_reset=reset)

        payload, problem = got["last"]
        if problem:
            note(problem, "最後訊息")
        else:
            try:
                recent = self._messages(payload, dot)
            except Problem as bad:
                note(bad, "最後訊息")
                recent = []
            if recent:
                last = recent[-1]
                parts.append(f"最後訊息 {local_stamp(last.at)} {last.speaker}")
                details.update(last_message_at=iso(last.at), last_speaker=last.speaker)
                preview = dot.get("messaging_room_preview") if isinstance(dot.get("messaging_room_preview"), dict) else {}
                read_at = parse_time(preview.get("last_read_at"))
                unread = bool(last.at and read_at and last.at > read_at)
                if last.from_agent:
                    flag = "，未讀" if unread else ""
                    status.waiting.append(
                        f"{name} 最後一句是 dot 說的（{local_stamp(last.at)}{flag}）：{one_line(last.text, 60)}"
                    )
            else:
                parts.append("還沒有訊息")

        status.summary = " · ".join(parts)
        status.details = details
        return Result.ok(status)

    # --- read -----------------------------------------------------------

    def read(self, cursors: dict, *, since: datetime | None = None, limit: int = MESSAGE_LIMIT) -> Result:
        limit = max(1, min(limit, MESSAGE_LIMIT_MAX))
        with ThreadPoolExecutor(max_workers=3) as pool:
            list_job = pool.submit(self._try, "list", timeout=45)
            msg_job = pool.submit(self._try, "messages", "--limit", str(limit), timeout=60)
            act_job = pool.submit(self._try, "activity", timeout=90) if self.include_activity else None
            dots, problem = list_job.result()
            raw_messages, msg_problem = msg_job.result()
            activity = act_job.result() if act_job else None
        if problem:
            return Result.failed(problem.error, problem.hint)
        try:
            dot = self._pick(dots)
        except Problem as bad:
            return Result.failed(bad.error, bad.hint)
        name = dot_name(dot)
        outcome = ReadOutcome()

        if msg_problem:
            outcome.failures.append(SourceFailure(f"{name} 訊息", msg_problem.error, msg_problem.hint))
        else:
            try:
                messages = self._messages(raw_messages, dot)
            except Problem as bad:
                return Result.failed(bad.error, bad.hint)
            raw_count = len(raw_messages["messages"] if isinstance(raw_messages, dict) else raw_messages)
            outcome.batches.append(
                window_delta("dot.messages", name, messages, cursors.get("dot.messages"), since, raw_count >= limit, limit)
            )

        if activity is not None:
            payload, act_problem = activity
            if act_problem:
                outcome.failures.append(SourceFailure(f"{name} 活動", act_problem.error, act_problem.hint))
            else:
                body = _body(payload)
                items = [activity_message(item, name) for item in body.get("data") or [] if isinstance(item, dict)]
                items.sort(key=lambda m: m.at.timestamp() if m.at else 0.0)
                more = bool(body.get("next_cursor")) and bool(items)
                outcome.batches.append(
                    window_delta("dot.activity", f"{name} 活動", items, cursors.get("dot.activity"), since, more, len(items))
                )
        return Result.ok(outcome)

    def schedules(self) -> Result:
        payload, problem = self._try("automations", timeout=45)
        if problem:
            return Result.failed(problem.error, problem.hint)
        return Result.ok(parse_schedules(payload))

    # --- send / wait ----------------------------------------------------

    def send(self, target: str | None, text: str, nonce: str) -> Result:
        if not self.binary:
            return Result.failed("找不到 chatgpt-dot-cli", FIX_INSTALL)
        body = with_nonce(text, nonce)
        if body.startswith("--auth"):
            return Result.failed("開頭是 --auth 的文字會被 chatgpt-dot-cli 當成參數，沒有送出", "換個開頭再送")
        argv = [self.binary, "--json", "send"]
        if self.dot_id:
            argv += ["--dot-id", self.dot_id]
        argv += ["--", body]
        sent_at = self.now()
        proc = self.runner.run(argv, timeout=90)
        if proc.code in (2, 127) and not proc.timed_out:
            error = "找不到 chatgpt-dot-cli" if proc.code == 127 else "ChatGPT 登入檔不能用"
            return Result.failed(f"{error}，沒有送出", FIX_INSTALL if proc.code == 127 else FIX_LOGIN)
        if proc.code == 0:
            try:
                payload = json.loads(proc.out)
            except json.JSONDecodeError:
                payload = {}
            key = payload.get("id") if isinstance(payload, dict) else None
            return Result.ok(SendReceipt(self.label, "", nonce, sent_at, "accepted", message_key=str(key or "")))
        error = "送出逾時" if proc.timed_out else short_error(proc.err) or f"exit {proc.code}"
        return Result.ok(SendReceipt(self.label, "", nonce, sent_at, "unknown", error=error))

    def wait(self, receipt: SendReceipt, *, timeout: float, poll: float) -> Result:
        deadline = self.clock() + timeout
        polls = 0
        delivered: bool | None = None
        mine_at: datetime | None = None
        last_error = ""
        dot: dict | None = None
        while True:
            polls += 1
            try:
                if dot is None:
                    dot = self._pick(self._cli("list", timeout=45))
                messages = self._messages(self._cli("messages", "--limit", str(MESSAGE_LIMIT), timeout=60), dot)
                reply = None
                index = next(
                    (
                        i
                        for i, m in enumerate(messages)
                        if not m.from_agent
                        and ((receipt.message_key and m.key == receipt.message_key) or has_nonce(m.text, receipt.nonce))
                    ),
                    None,
                )
                if index is not None:
                    delivered = True
                    mine_at = messages[index].at or mine_at
                    reply = next((m for m in messages[index + 1 :] if m.from_agent), None)
                elif delivered and mine_at:
                    reply = next((m for m in messages if m.from_agent and m.at and m.at > mine_at), None)
                elif delivered is None:
                    delivered = False
                if reply:
                    return Result.ok(WaitOutcome(True, reply, False, polls))
            except Problem as problem:
                last_error = problem.error
                if "無法從 JSON 判斷" in problem.error:
                    return Result.failed(problem.error, problem.hint)
            remaining = deadline - self.clock()
            if remaining <= 0:
                return Result.ok(WaitOutcome(delivered, None, True, polls, last_error))
            self.sleep(min(poll, remaining))


def activity_message(item: dict, name: str) -> Message:
    at = None
    for key in ("created_at", "timestamp", "occurred_at", "updated_at", "time"):
        at = parse_time(item.get(key))
        if at:
            break
    text = ""
    for key in ("title", "summary", "text", "description", "message", "preview", "type", "kind"):
        if isinstance(item.get(key), str) and item[key].strip():
            text = item[key]
            break
    return Message(source=f"{name} 活動", speaker="dot", text=text, at=at, from_agent=True, key=str(item.get("id") or ""))


def window_delta(
    cursor_key: str,
    label: str,
    items: list[Message],
    cursor: dict | None,
    since: datetime | None,
    window_full: bool,
    limit: int,
) -> Batch:
    """New items in a newest-N window, and whether older unseen items may exist."""
    newest = next((m for m in reversed(items) if m.key), None)
    new_cursor = {"id": newest.key, "at": iso(newest.at)} if newest else cursor
    oldest_at = items[0].at if items else None
    if since is not None:
        new = [m for m in items if m.at and m.at > since]
        gap = window_full and bool(oldest_at and oldest_at > since)
        note = f"--since 之後的訊息超過最近 {limit} 則，較舊的沒讀到" if gap else ""
        return Batch(cursor_key, label, new, new_cursor, gap, note)
    if not cursor or not cursor.get("id"):
        new = items[-FIRST_READ:]
        note = f"第一次讀取：只顯示最近 {len(new)} 則" if len(items) > len(new) else ""
        return Batch(cursor_key, label, new, new_cursor, False, note)
    keys = [m.key for m in items]
    if cursor["id"] in keys:
        return Batch(cursor_key, label, items[keys.index(cursor["id"]) + 1 :], new_cursor)
    cursor_at = parse_time(cursor.get("at"))
    new = [m for m in items if cursor_at is None or (m.at and m.at > cursor_at)]
    gap = window_full and (cursor_at is None or bool(oldest_at and oldest_at > cursor_at))
    note = f"上次讀到的位置已不在最近 {limit} 則內" if gap else ""
    return Batch(cursor_key, label, new, new_cursor, gap, note)
