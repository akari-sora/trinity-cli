"""Multiple Grok seats. These tests never start gbot."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from datetime import datetime, timezone

from tests.fakes import BOT_ID, FakeRunner, FakeSeat, GrokWorld, fail, grok_entry, unsupported_muse
from trinity_cli.model import Message, Result, SendReceipt, WaitOutcome
from trinity_cli.cli import main
from trinity_cli.config import (
    add_grok_seat,
    load_grok_seats,
    migrate_legacy_grok,
    remove_grok_seat,
    save_config,
)
from trinity_cli.grok_admin import discover, render_bots
from trinity_cli.seats.grok import FIX_AMBIGUOUS, GrokSeat, SANDBOX_GONE
from trinity_cli.state import State
from trinity_cli.targets import find_seat, grok_seats


class Fleet:
    """Several gbot logins. A 404 login has no bots."""

    def __init__(self, logins):
        self.logins = logins

    def __call__(self, args, stdin):
        account = None
        cleaned = []
        index = 0
        while index < len(args):
            if args[index] == "--account":
                account = args[index + 1]
                index += 2
                continue
            cleaned.append(args[index])
            index += 1
        if "--help" in cleaned:
            return _ok_text("thread\nbots\n--account NAME\n")
        if cleaned[:1] == ["accounts"]:
            return _ok({"accounts": [{"label": item["label"], "usable": True} for item in self.logins]})
        if cleaned[:2] == ["bots", "list"]:
            login = next(item for item in self.logins if item["label"] == account)
            if login.get("gone"):
                return fail(1, "HTTP 404 sandbox not found")
            return _ok([{"name": bot["name"], "description": bot.get("description", ""), "kind": "bot", "id": bot["id"]} for bot in login["bots"]])
        if cleaned[:1] == ["thread"]:
            return _ok({"transcript": {"entries": []}, "entryCount": 0})
        if cleaned[:1] == ["send"]:
            login = next(item for item in self.logins if item["label"] == account)
            if login.get("gone"):
                return fail(1, "HTTP 404 sandbox not found")
            login.setdefault("sent", []).append(stdin)
            bot = next(bot for bot in login["bots"] if bot["name"] == cleaned[1])
            return _ok({"id": bot["id"], "name": bot["name"], "kind": "bot"})
        raise AssertionError(cleaned)


def _ok(value):
    from trinity_cli.runner import Proc

    return Proc(0, json.dumps(value), "")


def _ok_text(text):
    from trinity_cli.runner import Proc

    return Proc(0, text, "")


def _seat(name, account, bot, fleet, *, default=False):
    return GrokSeat(
        FakeRunner(fleet),
        binary="gbot",
        seat_name=name,
        account=account,
        pinned_bot=bot,
        is_default=default,
        only_bots=[],
    )


class ConfigTests(unittest.TestCase):
    def test_legacy_keys_are_one_seat_named_grok(self):
        seats, default = load_grok_seats({"gbot_account": "example-login", "grok_bot": "Writer"})
        self.assertEqual(default, "grok")
        self.assertEqual([(seat.name, seat.account, seat.bot) for seat in seats], [("grok", "example-login", "Writer")])

    def test_named_seats_and_default(self):
        seats, default = load_grok_seats(
            {
                "grok_default": "researcher",
                "grok_seats": [
                    {"name": "researcher", "account": "login-a", "bot": "Researcher"},
                    {"name": "writer", "account": "login-b", "bot": "Writer", "enabled": False},
                    {"name": "dot", "account": "nope", "bot": "nope"},
                ],
            }
        )
        self.assertEqual(default, "researcher")
        self.assertEqual([seat.name for seat in seats if seat.enabled], ["researcher"])
        self.assertEqual(seats[1].enabled, False)

    def test_migration_backs_up_then_rewrites(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "config.json"
        save_config({"gbot_account": "example-login", "grok_bot": "Writer", "keep": True}, path)
        backup = migrate_legacy_grok(path)
        self.assertTrue(Path(backup).is_file())
        self.assertIn(b"gbot_account", Path(backup).read_bytes())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn("gbot_account", data)
        self.assertEqual(data["grok_default"], "grok")
        self.assertEqual(data["grok_seats"][0]["bot"], "Writer")
        self.assertTrue(data["keep"])
        self.assertIsNone(migrate_legacy_grok(path))

    def test_add_and_remove_keep_a_backup(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "config.json"
        save_config({"grok_seats": [{"name": "researcher", "account": "login-a", "bot": "Researcher"}], "grok_default": "researcher"}, path)
        backup = add_grok_seat("writer", "login-b", "Writer", path=path)
        self.assertTrue(str(backup).endswith(".bak-" + Path(backup).name.split(".bak-")[1][:15]) or Path(backup).is_file())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual([item["name"] for item in data["grok_seats"]], ["researcher", "writer"])
        remove_grok_seat("writer", path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual([item["name"] for item in data["grok_seats"]], ["researcher"])

    def test_config_write_uses_replace_and_utf8(self):
        source = Path(__import__("trinity_cli.config", fromlist=["save_config"]).__file__).read_text(encoding="utf-8")
        # The helper under test is save_config in this module's import.
        from trinity_cli import config as config_mod

        text = Path(config_mod.__file__).read_text(encoding="utf-8")
        self.assertIn("os.replace", text)
        self.assertNotIn("fcntl", text)
        self.assertNotIn("shell=True", text)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "config.json"
        save_config({"grok_seats": [{"name": "researcher", "account": "login-a", "bot": "研究員"}]}, path)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["grok_seats"][0]["bot"], "研究員")
        self.assertIsNotNone(source)


def _replied(key, family=None):
    def send(target, text, nonce):
        return Result.ok(SendReceipt(key, key, nonce, datetime.now(timezone.utc), "accepted"))

    reply = Message(key, "bot", "OK", datetime.now(timezone.utc), True)
    return FakeSeat(key, key, send=send, wait=Result.ok(WaitOutcome(True, reply, False, 1)), family=family)


class FanOutTests(unittest.TestCase):
    def seats(self):
        fleet = Fleet(
            [
                {
                    "label": "login-a",
                    "bots": [
                        {"id": "id-a", "name": "Researcher", "description": "box a"},
                        {"id": "id-old", "name": "Writer", "description": ""},
                    ],
                },
                {"label": "login-b", "bots": [{"id": "id-b", "name": "Writer", "description": "box b"}], "gone": True},
            ]
        )
        return fleet, [
            _replied("dot"),
            _seat("researcher", "login-a", "Researcher", fleet, default=True),
            _seat("writer", "login-b", "Writer", fleet),
            unsupported_muse(),
        ]

    def test_any_seat_name_from_grok_add_is_a_grok_seat(self):
        _fleet, seats = self.seats()
        self.assertEqual([seat.key for seat in grok_seats(seats)], ["researcher", "writer"])
        self.assertIs(find_seat(seats, "grok"), seats[1])

    def test_same_bot_name_on_two_logins_needs_an_account(self):
        fleet, seats = self.seats()
        seats.append(_seat("helper", "login-a", "Writer", fleet))
        err = io.StringIO()
        code = main(["ask", "grok", "--bot", "Writer", "hi"], seats=seats, out=io.StringIO(), err=err, ledger=_book())
        self.assertEqual(code, 2)
        self.assertIn("--account", err.getvalue())
        out = io.StringIO()
        code = main(
            ["ask", "grok", "--bot", "Writer", "--account", "login-a", "hi", "--timeout", "0"],
            seats=seats,
            out=out,
            err=io.StringIO(),
            ledger=_book(),
        )
        self.assertEqual(code, 1)
        sent = fleet.logins[0].get("sent") or []
        self.assertEqual(len(sent), 1)
        self.assertIn("[trinity ", sent[0])

    def test_all_keeps_going_when_one_grok_seat_is_unreachable(self):
        fleet, seats = self.seats()
        seats[1] = _replied("researcher", family="grok")
        out = io.StringIO()
        book = _book()
        code = main(["ask", "all", "ping", "--timeout", "0", "--poll", "1"], seats=seats, out=out, err=io.StringIO(), ledger=book)
        text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("sandbox gone", text)
        self.assertIn("researcher", text)
        nonces = {row["nonce"] for row in book.records() if row.get("nonce")}
        self.assertGreaterEqual(len(nonces), 2)

    def test_exit_one_only_when_every_targeted_seat_fails(self):
        fleet, seats = self.seats()
        code = main(["status"], seats=[seats[2]], out=io.StringIO(), err=io.StringIO())
        self.assertEqual(code, 1)
        code = main(["status"], seats=seats[1:], out=io.StringIO(), err=io.StringIO())
        self.assertEqual(code, 0)

    def test_cursors_are_per_seat_and_move_only_after_printing(self):
        fleet = Fleet(
            [
                {"label": "login-a", "bots": [{"id": "id-a", "name": "Researcher"}]},
                {"label": "login-b", "bots": [{"id": "id-b", "name": "Writer"}]},
            ]
        )
        # Distinct transcripts via the fleet's thread handler is empty, so use GrokWorld seats.
        world_a = GrokWorld(transcripts={"id-a": [grok_entry("e1", "assistant", "from-a", "2026-10-01T01:00:00Z")]}, bots=[{"id": "id-a", "name": "Researcher", "kind": "bot"}])
        world_b = GrokWorld(transcripts={"id-b": [grok_entry("e9", "assistant", "from-b", "2026-10-01T01:00:00Z")]}, bots=[{"id": "id-b", "name": "Writer", "kind": "bot"}])
        seat_a = GrokSeat(FakeRunner(world_a), binary="gbot", seat_name="researcher", account="login-a", pinned_bot="Researcher", is_default=True, only_bots=[])
        seat_b = GrokSeat(FakeRunner(world_b), binary="gbot", seat_name="writer", account="login-b", pinned_bot="Writer", only_bots=[])
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        state = State(Path(tmp.name) / "state.json")
        out = io.StringIO()
        code = main(["digest", "--peek"], seats=[seat_a, seat_b], out=out, err=io.StringIO(), state=state)
        self.assertEqual(code, 0)
        self.assertIn("from-a", out.getvalue())
        self.assertIn("from-b", out.getvalue())
        self.assertFalse(state.path.exists())
        main(["digest"], seats=[seat_a, seat_b], out=io.StringIO(), err=io.StringIO(), state=state)
        cursors = state.cursors()
        self.assertIn("researcher.messages", cursors)
        self.assertIn("writer.messages", cursors)
        self.assertNotEqual(cursors["researcher.messages"], cursors["writer.messages"])
        self.assertNotIn(BOT_ID, json.dumps(cursors))

    def test_discovery_hides_ids_and_marks_the_dead_login(self):
        from trinity_cli.state import home

        fleet, seats = self.seats()
        path = home() / "config.json"
        save_config(
            {
                "grok_default": "researcher",
                "grok_seats": [
                    {"name": "researcher", "account": "login-a", "bot": "Researcher"},
                    {"name": "writer", "account": "login-b", "bot": "Writer"},
                ],
            },
            path,
        )
        self.addCleanup(path.unlink, missing_ok=True)
        rows = discover(seats[1].runner, "gbot")
        text = render_bots(rows)
        self.assertNotIn("id-a", text)
        self.assertNotIn("id-b", text)
        self.assertNotIn("id-old", text)
        self.assertIn("Researcher", text)
        self.assertIn("reachable", text)
        self.assertIn(SANDBOX_GONE, text)
        self.assertIn("seat researcher", text)
        self.assertIn("seat writer", text)
        reachable = [row for row in rows if row["reachable"]]
        self.assertEqual(len(reachable), 2)
        self.assertEqual(sum(1 for row in rows if not row["reachable"]), 1)
        self.assertIn("trinity-cli grok add", text)

    def test_a_new_user_is_told_how_to_add_a_seat(self):
        unseated = [{"account": "login-a", "name": "Helper", "description": "", "reachable": True, "reason": "", "seat": ""}]
        self.assertIn("trinity-cli grok add NAME --account LABEL --bot BOT --default", render_bots(unseated))
        self.assertIn("Grok Bot app", render_bots([]))
        self.assertIn("trinity-cli grok bots", render_bots([]))
        with mock.patch("trinity_cli.grok_admin.find_tool", return_value=None):
            missing = discover(runner=None)
        self.assertIn("TRINITY_GBOT", render_bots(missing))
        self.assertIn("trinity-cli grok add", FIX_AMBIGUOUS)


def _book():
    from trinity_cli.state import Ledger

    tmp = tempfile.TemporaryDirectory()
    # Leak the directory until process exit; tests are short.
    _book.dirs.append(tmp)
    return Ledger(Path(tmp.name) / "ledger.jsonl")


_book.dirs = []


class CommandTests(unittest.TestCase):
    def test_grok_add_help_is_present(self):
        from trinity_cli.cli import build_parser

        parser = build_parser()
        text = parser.format_help()
        self.assertIn("grok", text)
        code = main(["grok"], out=io.StringIO(), err=io.StringIO(), seats=[unsupported_muse()])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
