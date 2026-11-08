"""`trinity-cli migrate SEAT PLAN`: deliver a migration plan to Muse or Your dot, resumably.

The plan is written by another tool (grok-bot-cli `gbot migrate`). Each step is one message.
Delivery reuses ask: every send gets a nonce, goes into the ledger before it leaves, and is
confirmed by reading the seat back. A step whose delivery is unknown is never sent again on
its own: a later run first looks for its nonce in the chat, and resends only with
--resend-unknown. Progress lives in TRINITY_HOME/migrations/<plan id>.json, so a run that stops
(timeout, login expired, Ctrl-C) continues where it stopped.

After the steps: read-back checks (seat memory text, schedules) and acceptance questions whose
answers must contain tokens taken from the source data.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import takewhile
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
    import msvcrt

from trinity_cli.app import ask_one
from trinity_cli.model import OK, ReadOutcome, SendReceipt, WaitOutcome
from trinity_cli.shown import Shown
from trinity_cli.state import Ledger, home
from trinity_cli.util import WINDOW_CURSOR, has_nonce, new_nonce, one_line

PLAN_FORMAT = "trinity-migration-plan"
PLAN_VERSION = 1
SEATS = ("muse", "dot")
MAX_STEPS = 400
MAX_TEXT = 16_000
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_MARKER = re.compile(r"Q\d+:")
_SHA256 = re.compile(r"[0-9a-fA-F]{64}")
# The whole read window, not the first-read tail an empty cursor gets.
_WINDOW = {"*": dict(WINDOW_CURSOR), "dot.messages": dict(WINDOW_CURSOR)}


class PlanError(ValueError):
    pass


def load_plan(path: str | Path) -> dict:
    """Read and validate a plan. Unknown fields are refused so a typo cannot skip a check."""
    try:
        raw = Path(path).expanduser().read_text(encoding="utf-8")
        plan = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlanError(f"讀不到搬家計畫：{exc}") from None
    if not isinstance(plan, dict) or plan.get("format") != PLAN_FORMAT or plan.get("version") != PLAN_VERSION:
        raise PlanError("不是 trinity-migration-plan v1")
    allowed = {"format", "version", "id", "seat", "title", "chat", "checkChat", "source", "steps", "checks", "questions", "notMigrated"}
    if extra := set(plan) - allowed:
        raise PlanError(f"計畫有不認得的欄位：{', '.join(sorted(extra))}")
    if not isinstance(plan.get("id"), str) or not _ID.match(plan["id"]):
        raise PlanError("計畫 id 不合法")
    if plan.get("seat") not in SEATS:
        raise PlanError("seat 只能是 muse 或 dot")
    for key in ("chat", "checkChat"):
        if key in plan and (not isinstance(plan[key], dict) or set(plan[key]) - {"title"} or not isinstance(plan[key].get("title"), str) or not plan[key]["title"].strip()):
            raise PlanError(f"{key} 只能有 title")
    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps or len(steps) > MAX_STEPS:
        raise PlanError("steps 必須是 1..400 則")
    seen: set[str] = set()
    for step in steps:
        if not isinstance(step, dict) or set(step) - {"id", "text", "expectReply", "attach"}:
            raise PlanError("step 欄位不對")
        if "attach" in step:
            step["attach"] = _attachments(step)
        if not isinstance(step.get("id"), str) or not _ID.match(step["id"]) or step["id"] in seen:
            raise PlanError("step id 不合法或重複")
        seen.add(step["id"])
        if not isinstance(step.get("text"), str) or not step["text"].strip() or len(step["text"]) > MAX_TEXT:
            raise PlanError(f"step {step['id']} 的內容是空的或超過 {MAX_TEXT} 字")
        if "expectReply" in step and not _tokens_ok(step["expectReply"]):
            raise PlanError(f"step {step['id']} 的 expectReply 不對")
    for check in plan.get("checks") or []:
        if not isinstance(check, dict) or check.get("kind") not in ("memory", "schedules") or not _tokens_ok(check.get("contains")) or set(check) - {"id", "kind", "contains", "min", "informational"} \
                or not _min_ok(check, check["contains"]) or not isinstance(check.get("informational", False), bool):
            raise PlanError("checks 欄位不對")
    for q in plan.get("questions") or []:
        if not isinstance(q, dict) or not isinstance(q.get("text"), str) or not _tokens_ok(q.get("expect")) or set(q) - {"id", "area", "text", "expect", "min", "note", "marker"} \
                or not _min_ok(q, q["expect"]) or ("marker" in q and not (isinstance(q["marker"], str) and _MARKER.fullmatch(q["marker"]))):
            raise PlanError("questions 欄位不對")
    return plan


def _attachments(step: dict) -> list[dict]:
    """The step's files as {"path", "sha256"}, hashed now. A file the plan gives with a sha256
    (or one already checked) must still have exactly those bytes."""
    files = step["attach"]
    if not isinstance(files, list) or not 1 <= len(files) <= 10:
        raise PlanError(f"step {step.get('id')} 的 attach 要是 1..10 個檔案")
    out = []
    for item in files:
        if isinstance(item, dict) and set(item) == {"path", "sha256"} and isinstance(item["sha256"], str) and _SHA256.fullmatch(item["sha256"]):
            path, want = item["path"], item["sha256"].lower()
        else:
            path, want = item, None
        if not isinstance(path, str) or not Path(path).is_absolute():
            raise PlanError(f"step {step.get('id')} 的 attach 要是絕對路徑，或 {{\"path\": 絕對路徑, \"sha256\": 64 個十六進位字}}")
        if not Path(path).is_file() or Path(path).is_symlink():
            raise PlanError(f"step {step.get('id')} 要附的檔案不存在或不是一般檔案：{path}")
        try:
            with open(path, "rb") as fh:
                have = hashlib.file_digest(fh, "sha256").hexdigest()
        except OSError as exc:
            raise PlanError(f"step {step.get('id')} 要附的檔案讀不到：{path}（{exc}）") from None
        if want and have != want:
            raise PlanError(f"step {step.get('id')} 要附的檔案內容和計畫寫的 sha256 不同，沒有送出：{path}")
        out.append({"path": path, "sha256": have})
    return out


def _min_ok(item: dict, tokens: list) -> bool:
    need = item.get("min", len(tokens))
    return isinstance(need, int) and not isinstance(need, bool) and 1 <= need <= len(tokens)


def _tokens_ok(value) -> bool:
    return isinstance(value, list) and all(
        isinstance(t, str) and t or (isinstance(t, list) and t and all(isinstance(a, str) and a for a in t)) for t in value
    )


def _norm(text: str) -> str:
    """Lowercase letters and digits only, so `squash-merge` matches "squash merge"."""
    return re.sub(r"[\W_]+", "", (text or "").lower())


def _hits(text: str, tokens: list) -> list:
    lower, flat = (text or "").lower(), _norm(text)
    return [t for t in tokens if any(a.lower() in lower or (_norm(a) and _norm(a) in flat) for a in (t if isinstance(t, list) else [t]))]


def _missing(text: str, tokens: list) -> list:
    hits = _hits(text, tokens)
    return [t for t in tokens if t not in hits]


def _has_marker(text: str, marker: str) -> bool:
    """`marker` (`Q1:`) opens the reply, after whitespace and markdown decoration. `Q10:` is not `Q1:`."""
    return (text or "").lstrip(" \t\r\n*_>#`").startswith(marker)


def _digest(step: dict) -> str:
    """What was sent: the text, plus the sha256 of every attached file (checked by load_plan)."""
    h = hashlib.sha256(step["text"].encode("utf-8"))
    for item in step.get("attach") or []:
        h.update(b"\0" + item["sha256"].encode("ascii"))
    return h.hexdigest()


def state_path(plan_id: str) -> Path:
    return home() / "migrations" / f"{plan_id}.json"


def _load_state(path: Path, plan: dict) -> dict:
    """A missing file is a fresh start. Any other unreadable file stops the run: starting over
    would send every step again."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"plan_id": plan["id"], "seat": plan["seat"], "steps": {}, "started_at": _iso(datetime.now(timezone.utc))}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlanError(f"進度檔讀不懂，沒有送出：{path}（{exc}）") from None
    if not isinstance(data, dict) or data.get("plan_id") != plan["id"] or data.get("seat") != plan["seat"]:
        raise PlanError(f"進度檔不是這份計畫的，沒有送出：{path}")
    if not _state_ok(data):
        raise PlanError(f"進度檔的欄位不對，沒有送出：{path}")
    return data


_NONE = type(None)
_STATE = {"plan_id": str, "seat": str, "steps": dict, "started_at": str, "chat_target": str, "finished_at": (str, _NONE), "last_send_at": str}
_RECORD = {"state": str, "nonce": str, "digest": str, "ask_id": str, "attempts": int, "at": str,
           "send": str, "readback": str, "reply": str, "replied_at": (str, _NONE)}
_RECORD_NEEDS = {"state", "nonce", "digest", "ask_id", "attempts", "at"}


def _state_ok(data: dict) -> bool:
    """Only fields this module writes, with the types it writes: a record it cannot trust could
    make a sent step look unsent."""
    if set(data) - set(_STATE) or "steps" not in data or any(not isinstance(v, _STATE[k]) for k, v in data.items()):
        return False
    for record in data["steps"].values():
        if not isinstance(record, dict) or set(record) - set(_RECORD) or not _RECORD_NEEDS <= set(record) \
                or any(not isinstance(v, _RECORD[k]) for k, v in record.items()) or isinstance(record["attempts"], bool) or not record["nonce"]:
            return False
    if "last_send_at" in data:
        try:
            if datetime.fromisoformat(data["last_send_at"]).tzinfo is None:
                return False
        except ValueError:
            return False
    return True


def _save_state(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


@contextmanager
def _locked(path: Path):
    """One run per plan at a time: a second run stops instead of sending the same step again."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = path.with_name(path.name + ".lock")
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            if fcntl:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            raise PlanError(f"這份計畫已經有另一個 migrate 在跑（{lock}），沒有送出。等它結束再跑。") from None
        yield
    finally:
        os.close(fd)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _replies_after(seat, nonce: str, target: str | None):
    """The agent's messages after the one carrying `nonce`, up to the next message that is not the
    agent's (the next step's reply is not this step's). None when the nonce is not in the seat's
    read window (100 messages on Muse, 32 on dot)."""
    result = seat.read(_WINDOW, limit=100, chat=target) if target else seat.read(_WINDOW, limit=100)
    if result.state != OK or not isinstance(result.value, ReadOutcome) or not result.value.batches:
        return None
    items = result.value.batches[0].items
    index = next((i for i, m in enumerate(items) if not m.from_agent and has_nonce(m.text, nonce)), None)
    return None if index is None else [m for m in takewhile(lambda m: m.from_agent, items[index + 1:]) if not m.presentation]


def _find_reply(seat, nonce: str, target: str | None = None) -> tuple[bool, object]:
    """(nonce seen in the chat, the first agent reply after it or None)."""
    replies = _replies_after(seat, nonce, target)
    return replies is not None, (replies or [None])[0]


def _marked_reply(seat, nonce: str, target: str | None, matches, *, timeout: float, poll: float):
    """The first agent message after `nonce` for which `matches(text)` holds, waiting up to `timeout`.

    An always-on agent also sends messages of its own (alerts, briefs) into the same chat, so
    "the first reply after my message" can be somebody else's topic. A marked reply cannot.
    """
    import time as _time
    clock = getattr(seat, "clock", None) or _time.monotonic
    sleep = getattr(seat, "sleep", None) or _time.sleep
    deadline = clock() + timeout
    while True:
        found = next((m for m in _replies_after(seat, nonce, target) or [] if matches(m.text)), None)
        if found:
            return found
        if clock() >= deadline:
            return None
        sleep(min(poll, max(0.0, deadline - clock())))


@dataclass
class StepOutcome:
    id: str
    state: str
    ok: bool
    note: str = ""
    nonce: str = ""
    reply: str = ""


# Sends are spaced like a person using the app: one message at a time (each waits for its reply)
# and at least this many seconds between two sends to the same seat.
DEFAULT_MIN_INTERVAL = 20.0
_RATE_LIMIT = re.compile(r"429|rate.?limit|too many|quota|slow down|上限|太頻繁|過於頻繁", re.IGNORECASE)


class _Pacer:
    """Waits out the gap since the last send, also one from an earlier run: its wall-clock time
    is kept in the progress file (the caller saves it)."""

    def __init__(self, seat, min_interval: float, state: dict, now):
        import time as _time
        self.gap = max(0.0, float(min_interval))
        self.clock = getattr(seat, "clock", None) or _time.monotonic
        self.sleep = getattr(seat, "sleep", None) or _time.sleep
        self.state, self.now = state, now
        self.last: float | None = None
        if state.get("last_send_at"):
            elapsed = max(0.0, (now() - datetime.fromisoformat(state["last_send_at"])).total_seconds())
            self.last = self.clock() - elapsed

    def before_send(self) -> None:
        if self.last is not None:
            left = self.gap - (self.clock() - self.last)
            if left > 0:
                self.sleep(left)
        self.last = self.clock()
        self.state["last_send_at"] = _iso(self.now())


def _stop_note(sid: str, error: str) -> str:
    if _RATE_LIMIT.search(error or ""):
        return f"{sid}: 對方說訊息太頻繁（{error}），已停下，沒有重送。過一段時間再跑同一個指令，會從這一步接著做。"
    return f"{sid}: {error}"


def run_migration(seat, plan: dict, *, path: Path | None = None, **options) -> dict:
    """Deliver `plan` (see _migrate for the options). One run per plan at a time."""
    path = path or state_path(plan["id"])
    with _locked(path):
        return _migrate(seat, plan, path=path, **options)


def _migrate(seat, plan: dict, *, path: Path, ledger: Ledger, timeout: float, poll: float, resend_unknown: bool = False,
             questions: bool = True, redo: list[str] | None = None, check_only: bool = False,
             min_interval: float = DEFAULT_MIN_INTERVAL, now=lambda: datetime.now(timezone.utc)) -> dict:
    if check_only and redo:
        raise PlanError("--check-only 不送任何步驟，不能和 --redo 一起用")
    state = _load_state(path, plan)
    pacer = _Pacer(seat, min_interval, state, now)
    # --redo: steps the caller found broken on the destination (for example a file whose
    # digest did not match) are sent again even though they were answered before.
    known = {step["id"] for step in plan["steps"]}
    for sid in redo or []:
        if sid not in known:
            raise PlanError(f"--redo 的步驟不在計畫裡：{sid}")
        state["steps"].pop(sid, None)
    # A reply answers the text that was sent. If the plan's text changed since, it proves nothing.
    for step in plan["steps"]:
        record = state["steps"].get(step["id"])
        if record and record.get("send") != "not_sent" and record.get("digest") != _digest(step):
            raise PlanError(f"步驟 {step['id']} 送出後內容改過了，上次的回覆不算數，沒有送出。要送新內容就加 --redo {step['id']}")
    if redo:
        _save_state(path, state)
    outcomes: list[StepOutcome] = []
    stopped = ""
    target = None
    chat_note = ""
    if plan.get("chat") and hasattr(seat, "open_chat"):
        # A dedicated chat keeps the migration out of the main conversation (Muse side chat).
        target = state.get("chat_target")
        if not target and not check_only:
            opened = seat.open_chat(plan["chat"]["title"])
            if opened.state == OK:
                target = opened.value[0]
                state["chat_target"] = target
                _save_state(path, state)
            else:
                chat_note = f"沒開成專用聊天室（{opened.error}），改用目前的主聊天室"
    for step in plan["steps"]:
        sid = step["id"]
        record = state["steps"].get(sid, {})
        nonce = record.get("nonce", "")
        reply, note, fresh = None, "", True
        if record.get("state") == "replied":
            reply, note, fresh = record.get("reply", ""), "earlier run", False
        elif check_only:
            outcomes.append(StepOutcome(sid, "not delivered", False, "進度檔裡沒有這一步送達並回覆的紀錄（--check-only 不送）", nonce))
            continue
        elif nonce and record.get("send") != "not_sent":
            # Sent before: read the chat back instead of sending again.
            seen, found = _find_reply(seat, nonce, target)
            if seen and found is None:
                receipt = SendReceipt(seat.label, target or seat.label, nonce, now(), "accepted")
                waited = seat.wait(receipt, timeout=timeout, poll=poll)
                if waited.state == OK and isinstance(waited.value, WaitOutcome) and waited.value.reply:
                    found = waited.value.reply
            if seen and found is not None:
                record.update(state="replied", reply=found.text[:2000], replied_at=_iso(found.at))
                state["steps"][sid] = record
                _save_state(path, state)
                reply, note = found.text, "confirmed by read-back"
            elif seen:
                stopped = f"{sid}: 已送達但還沒有回覆，沒有重送。稍後再跑一次同一個指令。"
                outcomes.append(StepOutcome(sid, "waiting", False, stopped, nonce))
                break
            elif not resend_unknown:
                stopped = f"{sid}: 讀回看不到上次送出的訊息（送達狀態不明），沒有重送。先看聊天室，確定沒收到再加 --resend-unknown。"
                outcomes.append(StepOutcome(sid, "unknown", False, stopped, nonce))
                break
        if reply is None:
            if step.get("attach"):
                _attachments(step)  # hashed again: a file changed since load_plan stops here, before anything is recorded or sent
            nonce = new_nonce()
            ask_id = f"{now():%Y%m%dT%H%M%SZ}-migrate-{plan['id'][:12]}-{sid}"
            pacer.before_send()
            state["steps"][sid] = {"state": "sending", "nonce": nonce, "digest": _digest(step), "ask_id": ask_id,
                                   "attempts": record.get("attempts", 0) + 1, "at": _iso(now())}
            _save_state(path, state)
            row = ask_one(seat, target, step["text"], nonce, ask_id=ask_id, ledger=ledger, timeout=timeout, poll=poll, now=now,
                          attach=[item["path"] for item in step.get("attach") or []] or None)
            rec = state["steps"][sid]
            rec.update(state=row.state, send=row.send, readback=row.readback)
            if row.reply:
                rec.update(reply=row.reply.text[:2000], replied_at=_iso(row.reply.at))
            _save_state(path, state)
            if row.state != "replied":
                if row.state == "timed_out":
                    stopped = f"{sid}: 等不到回覆（{timeout:.0f} 秒），沒有重送。稍後再跑一次同一個指令，會先讀回再繼續。"
                else:
                    stopped = _stop_note(sid, row.error or row.state) + (f"（{row.hint}）" if row.hint else "")
                outcomes.append(StepOutcome(sid, row.state, False, stopped, nonce))
                break
            reply = row.reply.text
        # The reply is checked on every run, so a later run says what the first one said; only a
        # new matching reply after the nonce turns a miss into a pass.
        expect = step.get("expectReply") or []
        missing = _missing(reply, expect)
        if missing:
            # The first reply may be the agent's own unrelated message: look for one that matches.
            marked = _marked_reply(seat, nonce, target, lambda text, expect=expect: not _missing(text, expect),
                                   timeout=timeout if fresh else 0, poll=poll)
            if marked is not None:
                reply, missing = marked.text, []
                state["steps"][sid].update(reply=reply[:2000], replied_at=_iso(marked.at))
                _save_state(path, state)
        if _RATE_LIMIT.search(reply) and (missing or not expect):
            # The agent answered "too many messages": the next step would only get the same answer.
            stopped = f"{sid}: 回覆說訊息太頻繁（{one_line(reply, 200)}），已停下，下一步沒有送。過一段時間加 --redo {sid} 再跑同一個指令。"
            outcomes.append(StepOutcome(sid, "replied", False, stopped, nonce, reply[:500]))
            break
        outcomes.append(StepOutcome(sid, "replied", not missing, f"回覆缺少 {missing}" if missing else note, nonce, reply[:500]))

    checks, answers = [], []
    if not stopped:
        for check in plan.get("checks") or []:
            result = seat.memory() if check["kind"] == "memory" else seat.schedules()
            if result.state != OK:
                # A required check that cannot be read has not passed.
                checks.append({"id": check.get("id", check["kind"]), "kind": check["kind"], "state": result.state,
                               "ok": None if check.get("informational") else False, "informational": bool(check.get("informational")),
                               "note": result.error or "這個座位不支援讀回"})
                continue
            text = result.value if isinstance(result.value, str) else "\n".join(f"{i.title} {i.when}" for i in result.value)
            hits = _hits(text, check["contains"])
            need = check.get("min", len(check["contains"]))
            passed = len(hits) >= need
            checks.append({"id": check.get("id", check["kind"]), "kind": check["kind"], "state": "ok",
                           "ok": None if check.get("informational") else passed, "found": passed,
                           "informational": bool(check.get("informational")), "expected": check["contains"], "hits": hits})
        if questions and plan.get("questions"):
            # Ask where the migration messages are not visible (a fresh Muse side chat), so an answer
            # has to come from the agent's memory or its files, not from the conversation just sent.
            ask_target, check_chat, refused = target, None, ""
            if plan.get("checkChat"):
                # Always a new chat, with a title no earlier chat has; only a chat created here is deleted.
                # Without one the questions are not asked: answers from the delivery chat prove nothing.
                title = f"{plan['checkChat']['title']} · {plan['id'][:12]} {now():%Y%m%d-%H%M%S} {secrets.token_hex(3)}"
                opened = seat.open_chat(title, create_only=True) if hasattr(seat, "open_chat") else None
                if opened is not None and opened.state == OK and opened.value[1]:
                    ask_target = check_chat = opened.value[0]
                else:
                    refused = f"沒開成驗收用的新聊天室（{opened.error if opened is not None else '這個座位不能開新聊天室'}），驗收題沒有問，不算過"
                    chat_note = (chat_note + "；" if chat_note else "") + refused
            try:
                for q in plan["questions"]:
                    if refused:
                        answers.append({"area": q.get("area", ""), "ok": False, "state": "not_asked", "hits": [], "answer": "", "error": refused,
                                        "expect": q["expect"], "attempts": 0, "earlier": [], "fresh_chat": False, "note": q.get("note")})
                        continue
                    # Answers vary between runs: a failed question is asked once more (a new message
                    # with its own nonce); both answers stay in the result.
                    tries = []
                    marker = q.get("marker")
                    for _ in range(2):
                        nonce = new_nonce()
                        ask_id = f"{now():%Y%m%dT%H%M%SZ}-migrate-check-{plan['id'][:12]}"
                        pacer.before_send()
                        _save_state(path, state)
                        row = ask_one(seat, ask_target, q["text"], nonce, ask_id=ask_id, ledger=ledger, timeout=timeout, poll=poll, now=now)
                        text = row.reply.text if row.reply else ""
                        # Judged on the raw reply, before marker filtering can replace it.
                        limited = bool(_RATE_LIMIT.search(text))
                        if row.state == "replied" and marker and not _has_marker(text, marker):
                            marked = _marked_reply(seat, nonce, ask_target, lambda t, marker=marker: _has_marker(t, marker), timeout=timeout, poll=poll)
                            text = marked.text if marked is not None else ""
                            limited = limited or bool(_RATE_LIMIT.search(text))
                        hits = _hits(text, q["expect"])
                        need = q.get("min", len(q["expect"]))
                        tries.append({"ok": row.state == "replied" and len(hits) >= need, "state": row.state, "hits": hits,
                                      "answer": text[:1500], "error": row.error, "limited": limited})
                        # A rate-limit answer is not asked again: the retry would be one more message too many.
                        if tries[-1]["ok"] or row.state != "replied" or limited:
                            break
                    last = tries[-1]
                    answers.append({"area": q.get("area", ""), **last, "expect": q["expect"], "attempts": len(tries),
                                    "earlier": tries[:-1], "fresh_chat": bool(check_chat), "note": q.get("note")})
                    if last["state"] != "replied" or (not last["ok"] and last["limited"]):
                        # Not sent, timed out or "too many messages": the next question would fare the same.
                        reason = last["error"] or (last["answer"][:200] if last["state"] == "replied" else last["state"])
                        stopped = _stop_note(f"驗收 {q.get('area') or q['text'][:30]}", reason) + "；後面的驗收題沒有問。"
                        break
            finally:
                if check_chat and hasattr(seat, "close_chat"):
                    seat.close_chat(check_chat)
    ok = not stopped and all(o.ok for o in outcomes) and all(c["ok"] is not False for c in checks) and all(a["ok"] for a in answers) \
        and (bool(answers) or not (questions and plan.get("questions")))
    if not check_only:
        state["finished_at"] = _iso(now()) if not stopped else None
        _save_state(path, state)
    return {
        "plan_id": plan["id"], "seat": plan["seat"], "ok": ok, "stopped": stopped or None, "state_path": str(path),
        "chat": target, "chat_note": chat_note or None,
        "steps": [o.__dict__ for o in outcomes], "total_steps": len(plan["steps"]), "checks": checks, "questions": answers,
    }


def render(result: dict) -> str:
    lines = [f"搬家到 {result['seat']}：計畫 {result['plan_id'][:16]}" + ("（專用聊天室）" if result.get("chat") else "")]
    if result.get("chat_note"):
        lines.append(f"  – {result['chat_note']}")
    for s in result["steps"]:
        mark = "✓" if s["ok"] else "✗"
        lines.append(f"  {mark} {s['id']}: {s['state']}" + (f" — {s['note']}" if s["note"] and not s["ok"] else ""))
    done = sum(1 for s in result["steps"] if s["ok"])
    lines.append(f"  送出 {done}/{result['total_steps']} 步")
    for c in result["checks"]:
        mark = {True: "✓", False: "✗", None: "–"}[c["ok"]]
        extra = "（僅供參考）" if c.get("informational") else ""
        lines.append(f"  {mark} 讀回 {c['kind']}{extra}" + (f"：{c['note']}" if c.get("note") else f"（{len(c.get('hits', []))}/{len(c.get('expected', []))}）"))
    for a in result["questions"]:
        where = "（新聊天室）" if a.get("fresh_chat") else ""
        lines.append(f"  {'✓' if a['ok'] else '✗'} 驗收 {a['area']}{where}")
    if result["stopped"]:
        lines.append(f"停在：{result['stopped']}")
    lines.append("結果：搬完並驗證" if result["ok"] else "結果：還沒完成")
    lines.append(f"進度檔：{result['state_path']}")
    return "\n".join(lines)


def run_migrate_command(seats, seat_key: str, plan_path: str, *, yes: bool, timeout: float, poll: float,
                        resend_unknown: bool, questions: bool, ledger: Ledger, stdin, redo: list[str] | None = None,
                        check_only: bool = False, min_interval: float = DEFAULT_MIN_INTERVAL) -> Shown:
    try:
        plan = load_plan(plan_path)
    except PlanError as exc:
        return Shown(2, str(exc), {"ok": False, "error": str(exc)})
    if plan["seat"] != seat_key:
        msg = f"這份計畫是給 {plan['seat']} 的，不是 {seat_key}"
        return Shown(2, msg, {"ok": False, "error": msg})
    seat = next((s for s in seats if getattr(s, "key", "") == seat_key), None)
    if seat is None or not seat.supports("send"):
        msg = f"沒有可以傳訊的 {seat_key} 座位"
        return Shown(2, msg, {"ok": False, "error": msg})
    if not yes and not check_only:
        preview = f"會送 {len(plan['steps'])} 則訊息給 {seat.label}（{plan.get('title') or plan['id']}），再讀回並問 {len(plan.get('questions') or [])} 題驗收。"
        if not (stdin and stdin.isatty()):
            msg = preview + " 不是終端機：加 --yes 才會送。"
            return Shown(2, msg, {"ok": False, "sent": False, "error": msg})
        print(preview, file=sys.stderr)
        print("要送出嗎？[y/N] ", end="", file=sys.stderr, flush=True)
        if stdin.readline().strip().lower() not in ("y", "yes"):
            return Shown(2, "沒有送出。", {"ok": False, "sent": False})
    try:
        result = run_migration(seat, plan, ledger=ledger, timeout=timeout, poll=poll, resend_unknown=resend_unknown,
                               questions=questions, redo=redo, check_only=check_only, min_interval=min_interval)
    except PlanError as exc:
        return Shown(2, str(exc), {"ok": False, "error": str(exc)})
    return Shown(0 if result["ok"] else 1, render(result), result)
