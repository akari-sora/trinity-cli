import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from tests.fakes import (
    BOT_ID,
    FAKE_JWT,
    SECRETS,
    Clock,
    DotWorld,
    FakeRunner,
    GrokWorld,
    dot_message,
    fail,
    grok_entry,
)
from trinity_cli.cli import main
from trinity_cli.redact import scrub, scrub_ids
from trinity_cli.seats import DotSeat, GrokSeat, MuseSeat
from trinity_cli.state import Ledger, State

TOKEN_LIKE = re.compile(
    r"eyJ[A-Za-z0-9_-]{8,}\.|(?i:bearer\s+[A-Za-z0-9])|\bsk-[A-Za-z0-9]{16,}|\bgh[pousr]_[A-Za-z0-9]{16,}"
)


class ScrubTests(unittest.TestCase):
    def test_removes_tokens(self):
        text = (
            f"Authorization: Bearer abc.def-123 jwt {FAKE_JWT} "
            "key sk-proj1234567890abcdefXYZ gh ghp_1234567890abcdefghijklmn "
            'access_token="zzz" and a blob aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3z'
        )
        cleaned = scrub(text)
        self.assertIsNone(TOKEN_LIKE.search(cleaned), cleaned)
        self.assertNotIn("zzz", cleaned)
        self.assertNotIn("aB3dE5fG7hJ9", cleaned)

    def test_keeps_hashes_paths_and_words(self):
        text = "sha 3f0c9e1d2b4a59687766554433221100ffeeddcc at /Users/me/Documents/Codex/2026-09-07/work/file.md"
        self.assertEqual(scrub(text), text)

    def test_ids_are_removed_from_errors(self):
        cleaned = scrub_ids(f"failed for {BOT_ID} in room_fakeRoom0001abc")
        self.assertNotIn(BOT_ID, cleaned)
        self.assertNotIn("room_fakeRoom0001abc", cleaned)


class NoSecretsInOutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = State(Path(self.tmp.name) / "state.json")
        self.ledger = Ledger(Path(self.tmp.name) / "ledger.jsonl")
        self.clock = Clock()

    def tearDown(self):
        self.tmp.cleanup()

    def seats(self, dot_world, grok_world):
        return [
            DotSeat(FakeRunner(dot_world), binary="chatgpt-dot-cli", hostnames=set(), clock=self.clock, sleep=self.clock.sleep),
            GrokSeat(FakeRunner(grok_world), binary="/fake/bin/gbot", only_bots=[], clock=self.clock, sleep=self.clock.sleep),
            MuseSeat(),
        ]

    def run_all(self, dot_world, grok_world):
        texts = []
        for argv in (["status"], ["--json", "status"], ["digest", "--peek"], ["--json", "digest", "--peek"],
                     ["ask", "all", "hi", "--grok-bot", "蝴蝶", "--timeout", "0"],
                     ["--json", "ask", "all", "hi", "--grok-bot", "蝴蝶", "--timeout", "0"]):
            out = io.StringIO()
            main(argv, seats=self.seats(dot_world, grok_world), out=out, err=io.StringIO(),
                 state=self.state, ledger=self.ledger, stdin=io.StringIO(""))
            texts.append(out.getvalue())
        return "\n".join(texts)

    def assert_clean(self, text):
        self.assertIsNone(TOKEN_LIKE.search(text), text)
        for secret in SECRETS:
            self.assertNotIn(secret, text)

    def test_happy_path_prints_no_ids_or_tokens(self):
        dot_world = DotWorld(messages=[dot_message(1, "dot", "hello", "2026-10-01T01:00:00Z")])
        grok_world = GrokWorld(transcripts={BOT_ID: [grok_entry("e1", "assistant", "hi")]})
        self.assert_clean(self.run_all(dot_world, grok_world))

    def test_failures_print_no_ids_or_tokens(self):
        dot_world = DotWorld()
        for command in ("list", "usage", "computers", "env", "messages", "activity", "send"):
            dot_world.overrides[command] = fail(3, f"boom Bearer {FAKE_JWT} for acct {BOT_ID}")
        grok_world = GrokWorld()
        for command in ("bots", "thread", "send", "doctor"):
            grok_world.overrides[command] = fail(1, f"gateway said token={FAKE_JWT} agent {BOT_ID}")
        self.assert_clean(self.run_all(dot_world, grok_world))

    def test_token_inside_a_message_body_is_scrubbed(self):
        dot_world = DotWorld(messages=[dot_message(1, "dot", f"here: {FAKE_JWT}", "2026-10-01T01:00:00Z")])
        grok_world = GrokWorld(transcripts={BOT_ID: [grok_entry("e1", "assistant", "key sk-proj1234567890abcdefXYZ")]})
        self.assert_clean(self.run_all(dot_world, grok_world))

    def test_state_and_ledger_hold_no_tokens(self):
        dot_world = DotWorld(messages=[dot_message(1, "dot", "hello", "2026-10-01T01:00:00Z")])
        grok_world = GrokWorld(transcripts={BOT_ID: [grok_entry("e1", "assistant", "hi")]})
        out = io.StringIO()
        main(["digest"], seats=self.seats(dot_world, grok_world), out=out, err=io.StringIO(), state=self.state)
        self.run_all(dot_world, grok_world)
        stored = self.state.path.read_text() + self.ledger.path.read_text()
        self.assertIsNone(TOKEN_LIKE.search(stored))
        json.loads(self.state.path.read_text())

    def test_dot_seat_never_passes_an_auth_path(self):
        dot_world = DotWorld()
        seat = DotSeat(FakeRunner(dot_world), binary="chatgpt-dot-cli", hostnames=set(),
                       clock=self.clock, sleep=self.clock.sleep)
        seat.status()
        seat.read({})
        for call in seat.runner.calls:
            self.assertFalse(any("auth" in part for part in call["argv"]))


if __name__ == "__main__":
    unittest.main()
