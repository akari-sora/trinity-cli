"""Fake subprocesses and seats. Nothing here touches the network or sends anything."""

from __future__ import annotations

import io
import json

from trinity_cli.model import Result
from trinity_cli.runner import Proc
from trinity_cli.seats.base import Seat

DOT_ID = "tbo_fakeDot0001abc"
ROOM_ID = "room_fakeRoom0001abc"
ME = "user-meFake00000001"
DOT_MEMBER = "user-dotFake0000001"
BOT_ID = "0b0e7a8c-1111-4222-8333-444455556666"
BOT_ID_2 = "0b0e7a8c-9999-4222-8333-444455556666"
FAKE_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmYWtlLXVzZXIifQ.c2lnbmF0dXJlLWZha2UtMTIz"
SECRETS = (DOT_ID, ROOM_ID, ME, DOT_MEMBER, BOT_ID, BOT_ID_2, FAKE_JWT)


def ok(value: object) -> Proc:
    return Proc(0, json.dumps(value), "")


def fail(code: int, err: str, timed_out: bool = False) -> Proc:
    return Proc(code, "", err, timed_out)


class FakeRunner:
    """Routes argv to handler(args, stdin) where args drops the binary and a leading --json."""

    def __init__(self, handler):
        self.handler = handler
        self.calls: list[dict] = []

    def run(self, argv, *, stdin=None, timeout=60.0, env=None):
        self.calls.append({"argv": list(argv), "stdin": stdin, "env": env})
        args = list(argv[1:])
        if args and args[0] == "--json":
            args = args[1:]
        return self.handler(args, stdin)

    def commands(self) -> list[str]:
        out = []
        for call in self.calls:
            args = [a for a in call["argv"][1:] if a != "--json"]
            if args[:1] == ["--account"]:
                args = args[2:]
            out.append(args[0] if args else "")
        return out


class Clock:
    def __init__(self):
        self.t = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


class BrokenOut(io.StringIO):
    def write(self, text):
        raise OSError("stdout closed")


class FakeSeat(Seat):
    def __init__(self, key="fake", label="Fake", status=None, read=None, send=None, wait=None):
        self.key = key
        self.label = label
        self._status = status
        self._read = read
        self._send = send
        self._wait = wait
        self.send_calls = 0
        self.wait_calls = 0

    @staticmethod
    def _value(value, *args, **kwargs):
        if callable(value):
            return value(*args, **kwargs)
        return value if value is not None else Result.failed("not configured")

    def status(self):
        return self._value(self._status)

    def read(self, cursors, *, since=None, limit=30):
        return self._value(self._read, cursors, since=since, limit=limit)

    def send(self, target, text, nonce):
        self.send_calls += 1
        return self._value(self._send, target, text, nonce)

    def wait(self, receipt, *, timeout, poll):
        self.wait_calls += 1
        return self._value(self._wait, receipt, timeout=timeout, poll=poll)


# --- Your dot shapes (values are fake; shapes match chatgpt-dot-cli --json) ---


def dot_record(paused: bool = False, with_dot_member: bool = True, last_read_at: str = "2026-10-01T01:00:00Z") -> dict:
    members = [{"account_user_id": ME, "role": "user", "name": "me"}]
    if with_dot_member:
        members.append({"account_user_id": DOT_MEMBER, "aeon_id": "aeon_fake00000001", "role": "user", "name": ""})
    return {
        "id": DOT_ID,
        "display_name": "",
        "status": "active",
        "is_paused": paused,
        "aeon_kind": "orbit",
        "messaging_room_id": ROOM_ID,
        "messaging_room_preview": {
            "id": ROOM_ID,
            "members": members,
            "last_read_at": last_read_at,
            "message_preview": {"latest_item_timestamp": "2026-10-01T02:00:00Z", "preview": "..."},
        },
    }


def dot_message(index: int, who: str, text: str, at: str) -> dict:
    return {
        "id": f"msg_fake{index:08d}",
        "created_at": at,
        "role": "user",
        "account_user_id": DOT_MEMBER if who == "dot" else ME,
        "content": {"text": text, "attachments": []},
    }


def usage_payload(used: int = 20, reached: bool = False) -> dict:
    return {
        "status": 200,
        "body": {
            "plan_type": "pro",
            "account_id": "acct_fakeAccount0001",
            "rate_limit": {
                "allowed": not reached,
                "limit_reached": reached,
                "primary_window": {"used_percent": used, "reset_after_seconds": 539440},
            },
        },
    }


def computers_payload(this_mac: str = "MacBook-Pro-5.local", attached: bool = True) -> dict:
    return {
        "status": 200,
        "body": {
            "computers": [
                {"display_name": "dot", "kind": "openai_cloud", "is_attached": True},
                {"display_name": this_mac, "kind": "user", "is_attached": attached},
                {"display_name": "win_desktop", "kind": "user", "is_attached": False},
            ],
            "local_computer_access_disabled_by_admin": False,
        },
        "info": False,
    }


ENV_PAYLOAD = {"status": 200, "body": {"status": "connected", "capabilities": [{"type": "remote_desktop", "status": "ready"}]}}


class DotWorld:
    """A fake chatgpt-dot-cli backed by an in-memory message list."""

    def __init__(self, messages=None, dot=None, activity=None):
        self.messages = list(messages or [])
        self.dot = dot or dot_record()
        self.activity = activity if activity is not None else {"data": [], "next_cursor": "cur"}
        self.automations: list = []
        self.overrides: dict = {}
        self.sent: list[str] = []
        self.send_result = None

    def __call__(self, args, stdin):
        command = args[0]
        if command in self.overrides:
            value = self.overrides[command]
            return value(args) if callable(value) else value
        if command == "list":
            return ok([self.dot])
        if command == "usage":
            return ok(usage_payload())
        if command == "computers":
            return ok(computers_payload())
        if command == "env":
            return ok(ENV_PAYLOAD)
        if command == "activity":
            return ok({"status": 200, "body": self.activity, "info": False})
        if command == "automations":
            return ok({"status": 200, "body": {"items": self.automations, "future": True}, "info": False})
        if command == "messages":
            if args[1:2] and not args[1].startswith("--"):
                return fail(2, "messages does not take a positional dot id; use --dot-id")
            limit = int(args[args.index("--limit") + 1]) if "--limit" in args else 20
            chosen = self.messages[-limit:]
            name = self.dot.get("display_name") or "Your dot"
            return ok(
                {
                    "name": name,
                    "lines": [f"{item.get('id')}: {item.get('preview', '')}" for item in chosen],
                    "messages": chosen,
                    "note": None if chosen else "no messages yet (send creates the room)",
                    "extra": {"ignored": True},
                }
            )
        if command == "send":
            text = args[args.index("--") + 1]
            self.sent.append(text)
            if self.send_result is not None:
                return self.send_result
            message = dot_message(900 + len(self.sent), "you", text, "2026-10-01T03:00:00Z")
            self.messages.append(message)
            return ok(message)
        raise AssertionError(f"unexpected dot command {args}")


# --- Grok Bot shapes (gbot --json) --------------------------------------------


def grok_entry(entry_id: str, role: str, text: str, at: str | None = None) -> dict:
    entry = {"id": entry_id, "role": role, "text": text}
    if at:
        entry["createdAt"] = at
    return entry


class GrokWorld:
    """A fake gbot with one or more bots and per-bot transcripts."""

    def __init__(
        self,
        transcripts=None,
        supports_after: bool = False,
        bots=None,
        supports_account: bool = False,
        supports_instructions: bool = False,
        supports_schedules: bool = False,
    ):
        self.bots = bots or [{"id": BOT_ID, "name": "蝴蝶", "kind": "bot"}]
        self.transcripts = transcripts if transcripts is not None else {BOT_ID: []}
        self.supports_after = supports_after
        self.supports_account = supports_account
        self.supports_instructions = supports_instructions
        self.supports_schedules = supports_schedules
        self.instruction_text = ""
        self.updates: list[dict] = []
        self.schedule_items: list = []
        self.overrides: dict = {}
        self.sent: list[str] = []
        self.send_result = None
        self.doctor = {"gatewayAuthPresent": True, "grokBotAppSession": {"present": True, "usable": True}}

    def _bot(self, ref):
        for bot in self.bots:
            if ref in (bot["id"], bot["name"]):
                return bot
        return None

    def __call__(self, args, stdin):
        args = list(args)
        stripped = []
        index = 0
        while index < len(args):
            if args[index] == "--account":
                index += 2
                continue
            stripped.append(args[index])
            index += 1
        args = stripped
        if "--help" in args:
            lines = ["Usage: gbot [--json] <command>", "  thread <bot> [--limit N]" + (" [--after ID]" if self.supports_after else "")]
            if self.supports_account:
                lines.append("  --account NAME")
                lines.append("GBOT_ACCOUNT")
            if self.supports_instructions:
                lines.append("  bots get <id-or-name>")
                lines.append("  bots update <id-or-name> [--instructions TEXT]")
            if self.supports_schedules:
                lines.append("  routines list")
            return Proc(0, "\n".join(lines), "")
        command = args[0]
        if command in self.overrides:
            value = self.overrides[command]
            return value(args) if callable(value) else value
        if command == "doctor":
            return ok(self.doctor)
        if command == "bots" and args[1] == "list":
            return ok(self.bots)
        if command == "bots" and args[1] == "get":
            bot = self._bot(args[2])
            if bot is None:
                return fail(1, f'No bot or group named "{args[2]}"')
            return ok({"id": bot["id"], "name": bot["name"], "description": self.instruction_text, "kind": "bot", "futureField": 1})
        if command == "bots" and args[1] == "update":
            if "--instructions" not in args:
                return fail(1, "update needs --instructions")
            text = args[args.index("--instructions") + 1]
            self.updates.append({"ref": args[2], "text": text})
            self.instruction_text = text
            return ok({"name": args[2], "description": text, "kind": "bot"})
        if command == "routines":
            return ok({"items": self.schedule_items, "future": True})
        if command == "thread":
            bot = self._bot(args[1])
            if bot is None:
                return fail(1, f'No bot or group named "{args[1]}"')
            limit = int(args[args.index("--limit") + 1])
            entries = self.transcripts.get(bot["id"], [])[-limit:]
            payload = {
                "target": {"id": bot["id"], "name": bot["name"], "isGroup": False},
                "transcript": {"entries": entries},
                "watermark": {"ok": True},
            }
            if "--after" in args:
                after = args[args.index("--after") + 1]
                ids = [e["id"] for e in entries]
                if after in ids:
                    rest = entries[ids.index(after) + 1 :]
                    payload.update(transcript={"entries": rest}, cursor=ids[-1], entryCount=len(rest), gapReset=False)
                else:
                    payload.update(cursor=ids[-1] if ids else "", entryCount=len(entries), gapReset=True)
            return ok(payload)
        if command == "send":
            self.sent.append(stdin)
            if self.send_result is not None:
                return self.send_result
            bot = self._bot(args[1])
            if bot is None:
                return fail(1, f'No bot or group named "{args[1]}"')
            entries = self.transcripts.setdefault(bot["id"], [])
            entries.append(grok_entry(f"e{len(entries) + 1000}", "user", stdin))
            return ok({"id": bot["id"], "name": bot["name"], "kind": "bot", "result": {"ok": True}})
        raise AssertionError(f"unexpected gbot command {args}")


_MUSE_EXIT = {
    "ok": 0,
    "browser_down": 2,
    "session_expired": 2,
    "region_blocked": 2,
    "profile_busy": 2,
    "credential_permissions": 2,
    "ui_changed": 3,
    "timeout": 3,
    "unsupported": 4,
}
_MUSE_ERROR = {
    "browser_down": "browser is not available",
    "session_expired": "登入工作階段已失效",
    "region_blocked": "Muse 在這個地區無法使用",
    "profile_busy": "profile is busy",
    "credential_permissions": "credential file must be mode 600",
    "ui_changed": "Muse 頁面結構對不上",
    "timeout": "timed out waiting for the sent message to appear",
    "unsupported": "不支援",
}


class MuseWorld:
    """Shapes match muse-web-cli --json. This never starts a browser."""

    def __init__(self, *, unsupported: bool = False):
        self.unsupported = unsupported
        self.force: dict[str, str] = {}
        self.headless = True
        self.backend = "browser"
        self.pending_count = 0
        self.card = False
        self.pending_items: list[dict] = []
        self.messages: list[dict] = []
        self.groups: list[dict] = []
        self.memory_text = ""
        self.reply = ""
        self.timeout_send = False
        self.calls: list[list[str]] = []

    def _state(self, command: str) -> str:
        if self.unsupported:
            return "unsupported"
        return self.force.get(command, "ok")

    def __call__(self, args, stdin):
        items = [item for item in args if item != "--autostart"]
        command = items[0]
        rest = items[1:]
        if rest[:1] == ["--"]:
            rest = rest[1:]
        self.calls.append([command, *rest])
        if command == "send" and self.timeout_send:
            return fail(124, "muse-web-cli timed out", timed_out=True)
        state = self._state(command)
        error = None if state == "ok" else _MUSE_ERROR.get(state, "不支援")
        hint = "wrong hint" if state in {"session_expired", "browser_down"} else None
        if command == "status":
            return _muse_proc(
                state,
                {
                    "backend": self.backend,
                    "state": state,
                    "pending": self.pending_count,
                    "latest_assistant_is_card": self.card,
                    "headless": self.headless,
                    "error": error,
                    "hint": hint,
                    "missing": [],
                    "ignored": FAKE_JWT,
                },
            )
        if command == "messages":
            rows = self.messages if state == "ok" else []
            return _muse_proc(
                state,
                {
                    "backend": self.backend,
                    "state": state,
                    "name": "Muse",
                    "lines": [f"{row['role']}: {row['text']}" for row in rows],
                    "messages": rows,
                    "error": error,
                    "hint": hint,
                    "extra": FAKE_JWT,
                },
            )
        if command == "send":
            text = rest[-1] if rest else ""
            attempted = state in {"ok", "timeout"}
            sent = state == "ok"
            if sent:
                self.messages.append({"role": "user", "text": text, "presentation": False, "secret": FAKE_JWT})
                if self.reply:
                    self.messages.append({"role": "assistant", "text": self.reply, "presentation": False})
            return _muse_proc(
                state,
                {
                    "backend": self.backend,
                    "state": state,
                    "attempted": attempted,
                    "sent": sent,
                    "text": text,
                    "reply": self.reply if sent and self.reply else None,
                    "presentation": False,
                    "elapsed_ms": 5,
                    "error": error,
                    "hint": "nothing was sent again" if state == "timeout" else hint,
                },
            )
        if command == "pending":
            items = self.pending_items if state == "ok" else []
            return _muse_proc(
                state,
                {"backend": self.backend, "state": state, "count": len(items), "items": items, "error": error, "hint": hint},
            )
        if command == "upcoming":
            groups = self.groups if state == "ok" else []
            count = sum(len(group.get("items") or []) for group in groups)
            return _muse_proc(
                state,
                {
                    "backend": self.backend,
                    "state": state,
                    "count": count,
                    "groups": groups,
                    "error": error,
                    "hint": hint,
                },
            )
        if command == "memory":
            body = self.memory_text if state == "ok" else ""
            return _muse_proc(
                state,
                {
                    "backend": self.backend,
                    "state": state,
                    "chars": len(body),
                    "sections": [],
                    "text": body,
                    "error": error,
                    "hint": hint,
                },
            )
        raise AssertionError(f"unexpected muse-web-cli command {command}")


def _muse_proc(state: str, payload: dict) -> Proc:
    return Proc(_MUSE_EXIT.get(state, 3), json.dumps(payload), "")


def unsupported_muse():
    from trinity_cli.seats.muse import MuseSeat

    return MuseSeat(FakeRunner(MuseWorld(unsupported=True)), binary="muse-web-cli")
