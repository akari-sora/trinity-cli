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

import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from trinity_cli.app import ask_one
from trinity_cli.model import OK, Result, SendReceipt, WaitOutcome
from trinity_cli.shown import Shown
from trinity_cli.state import Ledger, home
from trinity_cli.util import has_nonce, new_nonce

PLAN_FORMAT = "trinity-migration-plan"
PLAN_VERSION = 1
SEATS = ("muse", "dot")
MAX_STEPS = 400
MAX_TEXT = 16_000
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


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
        if not isinstance(step, dict) or set(step) - {"id", "text", "expectReply"}:
            raise PlanError("step 欄位不對")
        if not isinstance(step.get("id"), str) or not _ID.match(step["id"]) or step["id"] in seen:
            raise PlanError("step id 不合法或重複")
        seen.add(step["id"])
        if not isinstance(step.get("text"), str) or not step["text"].strip() or len(step["text"]) > MAX_TEXT:
            raise PlanError(f"step {step['id']} 的內容是空的或超過 {MAX_TEXT} 字")
        if "expectReply" in step and not _tokens_ok(step["expectReply"]):
            raise PlanError(f"step {step['id']} 的 expectReply 不對")
    for check in plan.get("checks") or []:
        if not isinstance(check, dict) or check.get("kind") not in ("memory", "schedules") or not _tokens_ok(check.get("contains")) or set(check) - {"id", "kind", "contains", "min", "informational"}:
            raise PlanError("checks 欄位不對")
    for q in plan.get("questions") or []:
        if not isinstance(q, dict) or not isinstance(q.get("text"), str) or not _tokens_ok(q.get("expect")) or set(q) - {"id", "area", "text", "expect", "min", "note", "marker"}:
            raise PlanError("questions 欄位不對")
    return plan


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


def state_path(plan_id: str) -> Path:
    return home() / "migrations" / f"{plan_id}.json"


def _load_state(path: Path, plan: dict) -> dict:
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("plan_id") == plan["id"] and data.get("seat") == plan["seat"]:
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {"plan_id": plan["id"], "seat": plan["seat"], "steps": {}, "started_at": _iso(datetime.now(timezone.utc))}


def _save_state(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _find_reply(seat, nonce: str, target: str | None = None) -> tuple[bool, object]:
    """(nonce seen in the chat, the first agent reply after it or None)."""
    from trinity_cli.model import ReadOutcome
    result = seat.read({"*": {}}, limit=100, chat=target) if target else seat.read({"*": {}}, limit=100)
    if result.state != OK or not isinstance(result.value, ReadOutcome) or not result.value.batches:
        return False, None
    items = result.value.batches[0].items
    index = next((i for i, m in enumerate(items) if not m.from_agent and has_nonce(m.text, nonce)), None)
    if index is None:
        return False, None
    reply = next((m for m in items[index + 1:] if m.from_agent and not m.presentation), None)
    return True, reply


def _marked_reply(seat, nonce: str, target: str | None, marker: str, *, timeout: float, poll: float, clock=None, sleep=None):
    """The first agent message after `nonce` that contains `marker`, waiting up to `timeout`.

    An always-on agent also sends messages of its own (alerts, briefs) into the same chat, so
    "the first reply after my message" can be somebody else's topic. A marked reply cannot.
    """
    import time as _time
    clock = clock or getattr(seat, "clock", None) or _time.monotonic
    sleep = sleep or getattr(seat, "sleep", None) or _time.sleep
    from trinity_cli.model import ReadOutcome
    deadline = clock() + timeout
    want = _norm(marker)
    while True:
        result = seat.read({"*": {}}, limit=100, chat=target) if target else seat.read({"*": {}}, limit=100)
        if result.state == OK and isinstance(result.value, ReadOutcome) and result.value.batches:
            items = result.value.batches[0].items
            index = next((i for i, m in enumerate(items) if not m.from_agent and has_nonce(m.text, nonce)), None)
            if index is not None:
                found = next((m for m in items[index + 1:] if m.from_agent and not m.presentation and want in _norm(m.text)), None)
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


def run_migration(seat, plan: dict, *, ledger: Ledger, timeout: float, poll: float, resend_unknown: bool = False,
                  questions: bool = True, path: Path | None = None, redo: list[str] | None = None,
                  now=lambda: datetime.now(timezone.utc)) -> dict:
    path = path or state_path(plan["id"])
    state = _load_state(path, plan)
    # --redo: steps the caller found broken on the destination (for example a file whose
    # digest did not match) are sent again even though they were answered before.
    known = {step["id"] for step in plan["steps"]}
    for sid in redo or []:
        if sid not in known:
            raise PlanError(f"--redo 的步驟不在計畫裡：{sid}")
        state["steps"].pop(sid, None)
    if redo:
        _save_state(path, state)
    outcomes: list[StepOutcome] = []
    stopped = ""
    target = None
    chat_note = ""
    if plan.get("chat") and hasattr(seat, "open_chat"):
        # A dedicated chat keeps the migration out of the main conversation (Muse side chat).
        target = state.get("chat_target")
        if not target:
            opened = seat.open_chat(plan["chat"]["title"])
            if opened.state == OK:
                target = opened.value
                state["chat_target"] = target
                _save_state(path, state)
            else:
                chat_note = f"沒開成專用聊天室（{opened.error}），改用目前的主聊天室"
    for step in plan["steps"]:
        sid = step["id"]
        record = state["steps"].get(sid, {})
        if record.get("state") == "replied":
            outcomes.append(StepOutcome(sid, "replied", True, "earlier run", record.get("nonce", ""), record.get("reply", "")))
            continue
        nonce = record.get("nonce")
        if nonce and record.get("send") != "not_sent":
            # Sent before: read the chat back instead of sending again.
            seen, reply = _find_reply(seat, nonce, target)
            if seen and reply is None:
                receipt = SendReceipt(seat.label, target or seat.label, nonce, now(), "accepted")
                waited = seat.wait(receipt, timeout=timeout, poll=poll)
                if waited.state == OK and isinstance(waited.value, WaitOutcome) and waited.value.reply:
                    reply = waited.value.reply
            if seen and reply is not None:
                record.update(state="replied", reply=reply.text[:2000], replied_at=_iso(reply.at))
                state["steps"][sid] = record
                _save_state(path, state)
                outcomes.append(StepOutcome(sid, "replied", True, "confirmed by read-back", nonce, reply.text[:500]))
                continue
            if seen:
                stopped = f"{sid}: 已送達但還沒有回覆，沒有重送。稍後再跑一次同一個指令。"
                outcomes.append(StepOutcome(sid, "waiting", False, stopped, nonce))
                break
            if not resend_unknown:
                stopped = f"{sid}: 讀回看不到上次送出的訊息（送達狀態不明），沒有重送。先看聊天室，確定沒收到再加 --resend-unknown。"
                outcomes.append(StepOutcome(sid, "unknown", False, stopped, nonce))
                break
        nonce = new_nonce()
        ask_id = f"{now():%Y%m%dT%H%M%SZ}-migrate-{plan['id'][:12]}-{sid}"
        state["steps"][sid] = {"state": "sending", "nonce": nonce, "ask_id": ask_id, "attempts": record.get("attempts", 0) + 1, "at": _iso(now())}
        _save_state(path, state)
        row = ask_one(seat, target, step["text"], nonce, ask_id=ask_id, ledger=ledger, timeout=timeout, poll=poll, now=now)
        rec = state["steps"][sid]
        rec.update(state=row.state, send=row.send, readback=row.readback)
        if row.reply:
            rec.update(reply=row.reply.text[:2000], replied_at=_iso(row.reply.at))
        _save_state(path, state)
        if row.state == "replied":
            expect = step.get("expectReply") or []
            reply = row.reply
            missing = [t for t in expect if t not in _hits(reply.text, expect)]
            if missing:
                # The first reply may be the agent's own unrelated message: look for the marked one.
                marked = _marked_reply(seat, nonce, target, " ".join(expect), timeout=timeout, poll=poll)
                if marked is not None:
                    reply = marked
                    missing = []
                    rec.update(reply=reply.text[:2000], replied_at=_iso(reply.at))
                    _save_state(path, state)
            outcomes.append(StepOutcome(sid, "replied", not missing, f"回覆缺少 {missing}" if missing else "", nonce, reply.text[:500]))
            continue
        if row.state == "timed_out":
            stopped = f"{sid}: 等不到回覆（{timeout:.0f} 秒），沒有重送。稍後再跑一次同一個指令，會先讀回再繼續。"
        else:
            stopped = f"{sid}: {row.error or row.state}" + (f"（{row.hint}）" if row.hint else "")
        outcomes.append(StepOutcome(sid, row.state, False, stopped, nonce))
        break

    checks, answers = [], []
    if not stopped:
        for check in plan.get("checks") or []:
            result = seat.memory() if check["kind"] == "memory" else seat.schedules()
            if result.state != OK:
                checks.append({"id": check.get("id", check["kind"]), "kind": check["kind"], "state": result.state, "ok": None,
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
            ask_target, check_chat = target, None
            if plan.get("checkChat") and hasattr(seat, "open_chat"):
                opened = seat.open_chat(f"{plan['checkChat']['title']} · {now():%m%d-%H%M%S}")
                if opened.state == OK:
                    ask_target = check_chat = opened.value
                else:
                    chat_note = (chat_note + "；" if chat_note else "") + f"沒開成驗收用的新聊天室（{opened.error}），驗收題問在搬家聊天室，答案可能來自對話上下文"
            try:
                for q in plan["questions"]:
                    # Answers vary between runs: a failed question is asked once more (a new message
                    # with its own nonce); both answers stay in the result.
                    tries = []
                    for _ in range(2):
                        nonce = new_nonce()
                        ask_id = f"{now():%Y%m%dT%H%M%SZ}-migrate-check-{plan['id'][:12]}"
                        row = ask_one(seat, ask_target, q["text"], nonce, ask_id=ask_id, ledger=ledger, timeout=timeout, poll=poll, now=now)
                        text = row.reply.text if row.reply else ""
                        if row.state == "replied" and q.get("marker") and _norm(q["marker"]) not in _norm(text):
                            marked = _marked_reply(seat, nonce, ask_target, q["marker"], timeout=timeout, poll=poll)
                            text = marked.text if marked is not None else ""
                        hits = _hits(text, q["expect"])
                        need = q.get("min", len(q["expect"]))
                        tries.append({"ok": row.state == "replied" and len(hits) >= need, "state": row.state, "hits": hits,
                                      "answer": text[:1500], "error": row.error})
                        if tries[-1]["ok"] or row.state != "replied":
                            break
                    last = tries[-1]
                    answers.append({"area": q.get("area", ""), **last, "expect": q["expect"], "attempts": len(tries),
                                    "earlier": tries[:-1], "fresh_chat": bool(check_chat), "note": q.get("note")})
            finally:
                if check_chat and hasattr(seat, "close_chat"):
                    seat.close_chat(check_chat)
    ok = not stopped and all(o.ok for o in outcomes) and all(c["ok"] is not False for c in checks) and all(a["ok"] for a in answers) \
        and (bool(answers) or not (questions and plan.get("questions")))
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
                        resend_unknown: bool, questions: bool, ledger: Ledger, stdin, redo: list[str] | None = None) -> Shown:
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
    if not yes:
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
                               questions=questions, redo=redo)
    except PlanError as exc:
        return Shown(2, str(exc), {"ok": False, "error": str(exc)})
    return Shown(0 if result["ok"] else 1, render(result), result)
