"""Forward one seat's reply to another, and wait for a new reply. Never auto-chains."""

from __future__ import annotations

import re
import time
from datetime import datetime

from trinity_cli.app import ask_exit, ask_json, ask_one, call, render_ask
from trinity_cli.targets import find_seat
from trinity_cli.model import OK, UNSUPPORTED, Batch, Message, ReadOutcome, Result
from trinity_cli.redact import scrub
from trinity_cli.shown import Shown
from trinity_cli.state import Ledger
from trinity_cli.util import WINDOW_CURSOR, has_nonce, iso, local_stamp, new_nonce, now_utc, one_line, parse_time

_SPEC = re.compile(r"^(?P<seat>[A-Za-z][A-Za-z0-9-]*)(?::(?P<target>[^#]+))?(?:#(?P<sel>last|[1-9]\d*))?$")
_YES = {"y", "yes", "是"}


class AnnotatingLedger:
    """Adds provenance to every ledger line without copying the message body."""

    def __init__(self, inner: Ledger, extra: dict):
        self.path = inner.path
        self._inner = inner
        self._extra = extra

    def append(self, record: dict) -> None:
        self._inner.append({**self._extra, **record})

    def records(self) -> list[dict]:
        return self._inner.records()


def parse_spec(text: str) -> tuple[str, str | None, str | None]:
    match = _SPEC.match(text.strip())
    if not match:
        raise ValueError(f"看不懂 `{text}`（用 dot、grok:蝴蝶 或 grok:蝴蝶#last）")
    return match.group("seat"), match.group("target"), match.group("sel")


def _find(seats, key: str):
    return find_seat(seats, key)


def _label(seat, target: str | None) -> str:
    return f"{seat.label}/{target}" if target else seat.label


def _matches(batch: Batch, target: str) -> bool:
    return batch.label == target or batch.label.endswith("/" + target)


def _window(seat, target: str | None) -> tuple[list[Message], Result | None]:
    result = call(seat, "read", {"*": dict(WINDOW_CURSOR), "dot.messages": dict(WINDOW_CURSOR)}, limit=30 if seat.key == "dot" else 40)
    if result.state == UNSUPPORTED:
        return [], result
    if result.state != OK:
        return [], result
    outcome = result.value
    if not isinstance(outcome, ReadOutcome):
        return [], Result.failed(f"{seat.label} 讀取格式不對")
    batches = [batch for batch in outcome.batches if batch.cursor_key != "dot.activity" and not batch.label.endswith("活動")]
    if target:
        batches = [batch for batch in batches if _matches(batch, target)]
        if not batches:
            return [], Result.failed(f"找不到 {target}", "用 grok:<名字> 指定 bot")
    if outcome.failures and not batches:
        failure = outcome.failures[0]
        return [], Result.failed(failure.error, failure.hint)
    messages: list[Message] = []
    for batch in batches:
        messages.extend(batch.items)
    return messages, None


def _agents(messages: list[Message]) -> list[Message]:
    return [message for message in messages if message.from_agent and message.text.strip()]


def compose_hand(instruction: str, message: Message) -> str:
    who = f"{message.source} · {message.speaker} · {local_stamp(message.at)}"
    return f"{instruction.strip()}\n\n---\n轉自 {who}\n\n{message.text.strip()}\n---"


def _confirmed(yes: bool, stdin) -> bool:
    if yes:
        return True
    if not getattr(stdin, "isatty", lambda: False)():
        return False
    try:
        return stdin.readline().strip().lower() in _YES
    except (OSError, ValueError):
        return False


def _preview(source_label: str, dest_label: str, instruction: str, message: Message) -> str:
    body = compose_hand(instruction, message)
    return (
        "預覽（還沒送出）：\n"
        f"從 {source_label}（{local_stamp(message.at)}，{message.speaker}）\n"
        f"到 {dest_label}\n\n"
        f"{body}\n\n"
        "送出時會另起一行加上 [trinity …]，用來確認有送到。"
    )


def run_hand(
    seats,
    source: str,
    dest: str,
    instruction: str,
    *,
    yes: bool = False,
    timeout: float = 180.0,
    poll: float = 10.0,
    ledger: Ledger | None = None,
    stdin=None,
    now=now_utc,
) -> Shown:
    instruction = instruction.strip()
    if not instruction:
        return Shown(2, "沒有指令內容，沒有送出。", {"sent": False, "error": "missing instruction"})
    try:
        source_key, source_target, selector = parse_spec(source)
        dest_key, dest_target, _ = parse_spec(dest)
    except ValueError as exc:
        return Shown(2, str(exc), {"sent": False, "error": str(exc)})
    selector = selector or "last"
    origin = _find(seats, source_key)
    target_seat = _find(seats, dest_key)
    if origin is None or target_seat is None:
        missing = source_key if origin is None else dest_key
        return Shown(2, f"沒有 {missing} 這個座位。", {"sent": False, "error": "unknown seat"})
    messages, problem = _window(origin, source_target)
    if problem is not None:
        state = "unsupported" if problem.state == UNSUPPORTED else "failed"
        code = 0 if problem.state == UNSUPPORTED else 1
        text = f"– {problem.error}" if problem.state == UNSUPPORTED else f"✗ {problem.error}" + (f" → {problem.hint}" if problem.hint else "")
        return Shown(code, text + "\n沒有送出。", {"sent": False, "state": state, "error": problem.error, "hint": problem.hint})
    agents = _agents(messages)
    chosen = None
    nth = 1 if selector == "last" else int(selector)
    if nth <= len(agents):
        chosen = agents[-nth]
    if chosen is None:
        if agents and selector != "last":
            text = f"只有 {len(agents)} 則可轉交的回覆，沒有送出。"
        else:
            text = "沒有可轉交的回覆，沒有送出。"
        return Shown(1, text, {"sent": False, "error": "no reply"})
    dest_label = _label(target_seat, dest_target)
    if not target_seat.supports("send"):
        reason = target_seat.unsupported_reason
        return Shown(0, f"– {dest_label}：{reason}\n沒有送出。", {"sent": False, "state": "unsupported", "error": reason})
    preview = _preview(_label(origin, source_target), dest_label, instruction, chosen)
    data = {
        "sent": False,
        "confirmed": False,
        "from": {"seat": origin.key, "target": source_target, "speaker": chosen.speaker, "at": iso(chosen.at)},
        "to": {"seat": target_seat.key, "target": dest_target},
        "preview": preview,
    }
    if not _confirmed(yes, stdin):
        text = preview + "\n\n沒有確認，沒有送出。要送出請加上 --yes。"
        return Shown(2, text, data)
    data["confirmed"] = True
    body = compose_hand(instruction, chosen)
    nonce = new_nonce()
    ask_id = f"{now():%Y%m%dT%H%M%SZ}-{nonce}"
    book = ledger or Ledger()
    tagged = AnnotatingLedger(
        book,
        {
            "kind": "hand",
            "from_seat": origin.key,
            "from_target": _label(origin, source_target),
            "from_at": iso(chosen.at),
        },
    )
    row = ask_one(target_seat, dest_target, body, nonce, ask_id=ask_id, ledger=tagged, timeout=timeout, poll=poll, now=now)
    data["sent"] = row.send != "not_sent" and row.state != "unsupported"
    data.update(ask_json([row], ask_id=ask_id, nonce=nonce))
    rendered = render_ask([row], nonce=nonce, timeout=timeout, ledger_path=str(book.path))
    text = f"已轉交 {_label(origin, source_target)} → {dest_label}\n\n{rendered}"
    return Shown(ask_exit([row]), text, data)


def parse_hand_tail(argv: list[str]) -> tuple[dict, str | None]:
    """Parse `hand SOURCE --to DEST TEXT` from a wait --then tail."""
    yes = False
    timeout = 180.0
    poll = 10.0
    dest = None
    words: list[str] = []
    index = 0
    while index < len(argv):
        item = argv[index]
        if item == "--yes":
            yes = True
            index += 1
            continue
        if item in {"--to", "--timeout", "--poll"}:
            if index + 1 >= len(argv):
                return {}, f"{item} 缺少值"
            value = argv[index + 1]
            index += 2
            if item == "--to":
                dest = value
            else:
                try:
                    number = float(value)
                except ValueError:
                    return {}, f"{item} 看不懂：{value}"
                if item == "--timeout":
                    timeout = number
                else:
                    poll = number
            continue
        if item.startswith("--"):
            return {}, f"看不懂的參數 {item}"
        words.append(item)
        index += 1
    if not words:
        return {}, "hand 缺少來源"
    if not dest:
        return {}, "hand 缺少 --to"
    instruction = " ".join(words[1:]).strip()
    if not instruction:
        return {}, "hand 缺少指令，沒有送出"
    return {"source": words[0], "dest": dest, "instruction": instruction, "yes": yes, "timeout": timeout, "poll": poll}, None


def _target_matches(recorded: object, wanted: str | None) -> bool:
    if not wanted:
        return True
    text = recorded if isinstance(recorded, str) else ""
    return text == wanted or text.endswith("/" + wanted)


def marker_for(records: list[dict], seat: str, target: str | None):
    """How far a later reply has to be. Timeouts do not move the mark."""
    mark = {"after": None, "nonce": None, "awaiting": False, "reply_key": None}
    seen = False
    for record in records:
        if record.get("seat") != seat or not _target_matches(record.get("target"), target):
            continue
        seen = True
        event = record.get("event")
        if event in {"sent", "sending"} and isinstance(record.get("nonce"), str):
            mark["nonce"] = record["nonce"]
        if event == "sent":
            at = parse_time(record.get("sent_at")) or parse_time(record.get("at"))
            if at is not None:
                mark["after"] = at
                mark["awaiting"] = True
                mark["reply_key"] = None
        elif event == "result" and record.get("reply") == "replied":
            at = parse_time(record.get("replied_at")) or parse_time(record.get("at"))
            if at is not None:
                mark["after"] = at
            mark["awaiting"] = False
        elif event == "wait" and record.get("status") == "seen":
            at = parse_time(record.get("reply_at")) or parse_time(record.get("at"))
            if at is not None:
                mark["after"] = at
            if isinstance(record.get("reply_key"), str) and record["reply_key"]:
                mark["reply_key"] = record["reply_key"]
            mark["awaiting"] = False
    return mark if seen else None


def _next_agent(messages: list[Message], index: int) -> Message | None:
    return next((message for message in messages[index + 1 :] if message.from_agent and message.text.strip()), None)


def reply_after(messages: list[Message], mark: dict | None, baseline: set[str] | None) -> Message | None:
    if mark and mark.get("reply_key"):
        index = next((i for i, message in enumerate(messages) if message.key == mark["reply_key"]), None)
        if index is not None:
            return _next_agent(messages, index)
    if mark and mark.get("awaiting") and mark.get("nonce"):
        index = next((i for i, message in enumerate(messages) if not message.from_agent and has_nonce(message.text, mark["nonce"])), None)
        if index is not None:
            return _next_agent(messages, index)
    after = mark.get("after") if mark else None
    if isinstance(after, datetime):
        newer = [message for message in messages if message.from_agent and message.at and message.at > after and message.text.strip()]
        if newer:
            return min(newer, key=lambda message: message.at)
    if baseline is not None:
        fresh = [message for message in messages if message.from_agent and message.key and message.key not in baseline and message.text.strip()]
        if fresh:
            return fresh[0]
    return None


def _notify(notifier, err, title: str, body: str) -> None:
    if err is not None:
        try:
            err.write("\a")
            err.flush()
        except OSError:
            pass
    if notifier is None:
        return
    try:
        notifier(one_line(scrub(title), 60), one_line(scrub(body), 140))
    except Exception:
        return


def run_wait(
    seats,
    spec: str,
    *,
    timeout: float = 180.0,
    poll: float = 5.0,
    notify: bool = False,
    then_args: list[str] | None = None,
    ledger: Ledger | None = None,
    stdin=None,
    clock=None,
    sleep=None,
    notifier=None,
    err=None,
    now=now_utc,
) -> Shown:
    try:
        seat_key, target, _selector = parse_spec(spec)
    except ValueError as exc:
        return Shown(2, str(exc), {"state": "error", "error": str(exc)})
    seat = _find(seats, seat_key)
    if seat is None:
        return Shown(2, f"沒有 {seat_key} 這個座位。", {"state": "error", "error": "unknown seat"})
    if target is None:
        target = getattr(seat, "default_bot", None) or None
    if not seat.supports("read"):
        reason = seat.unsupported_reason
        return Shown(0, f"– {_label(seat, target)}：{reason}", {"state": "unsupported", "seat": seat.key, "error": reason, "sent": False})
    book = ledger or Ledger()
    mark = marker_for(book.records(), seat.key, target)
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    started = clock()
    deadline = started + timeout
    delay = poll if poll > 0 else 1.0
    baseline: set[str] | None = None
    polls = 0
    last_error = ""
    found: Message | None = None
    while True:
        polls += 1
        messages, problem = _window(seat, target)
        read_ok = True
        if problem is not None and problem.state == UNSUPPORTED:
            return Shown(0, f"– {problem.error}", {"state": "unsupported", "error": problem.error, "sent": False, "polls": polls})
        if problem is not None and problem.state != OK:
            last_error = problem.error
            messages = []
            read_ok = False
        else:
            found = reply_after(messages, mark, baseline)
            if found is not None:
                break
        if read_ok and baseline is None:
            baseline = {message.key for message in messages if message.key}
        remaining = deadline - clock()
        if remaining <= 0:
            found = None
            break
        sleep(min(delay, remaining))
        delay = min(max(delay * 2, delay), 30.0)
    elapsed = clock() - started
    label = _label(seat, target)
    if found is None:
        book.append({"event": "wait", "seat": seat.key, "target": label, "status": "timed_out", "polls": polls, "at": iso(now())})
        text = f"{label}：等了 {elapsed:.0f} 秒沒有新回覆，沒有重送。"
        if last_error:
            text += f"\n{last_error}"
        if notify:
            _notify(notifier, err, "trinity-cli", f"{label} 沒有新回覆")
        return Shown(1, text, {"state": "timed_out", "seat": seat.key, "target": target, "polls": polls, "sent": False, "error": last_error})
    book.append(
        {
            "event": "wait",
            "seat": seat.key,
            "target": label,
            "status": "seen",
            "polls": polls,
            "reply_at": iso(found.at) or iso(now()),
            "reply_key": found.key,
            "at": iso(now()),
        }
    )
    text = f"{label}：{local_stamp(found.at)} {found.speaker} 回覆\n\n{found.text.strip()}"
    if notify:
        _notify(notifier, err, "trinity-cli", f"{label} 有新回覆")
        text += "\n\n已通知。"
    data = {
        "state": "seen",
        "seat": seat.key,
        "target": target,
        "polls": polls,
        "sent": False,
        "reply": {"at": iso(found.at), "speaker": found.speaker, "text": found.text},
    }
    tail = list(then_args or [])
    if tail[:1] == ["--"]:
        tail = tail[1:]
    if not tail:
        return Shown(0, text, data)
    if tail[0] != "hand":
        return Shown(2, text + "\n\n--then 目前只接受 hand，沒有再送出。", {**data, "error": "bad then"})
    parsed, error = parse_hand_tail(tail[1:])
    if error:
        return Shown(2, text + f"\n\n{error}", {**data, "error": error})
    handed = run_hand(seats, ledger=book, stdin=stdin, now=now, **parsed)
    data["then"] = handed.data
    data["sent"] = bool(handed.data.get("sent"))
    return Shown(handed.code, text + "\n\n" + handed.text, data)
