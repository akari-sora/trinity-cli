import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tests.fakes import Clock, FakeSeat, unsupported_muse
from trinity_cli.cli import main
from trinity_cli.model import Batch, Message, ReadOutcome, Result, SendReceipt
from trinity_cli.state import Ledger


def batch(messages, key="dot.messages", label="Your dot"):
    return Result.ok(ReadOutcome([Batch(key, label, messages, None)]))


def msg(text, *, agent=True, at="2026-10-01T04:00:00Z", key="a1"):
    return Message("Your dot", "dot" if agent else "you", text, datetime.fromisoformat(at.replace("Z", "+00:00")), agent, key)


class WaitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / "ledger.jsonl")
        self.clock = Clock()

    def tearDown(self):
        self.tmp.cleanup()

    def invoke(self, seats, *argv, notifier=None):
        out, err = io.StringIO(), io.StringIO()
        code = main(
            list(argv),
            seats=seats,
            out=out,
            err=err,
            ledger=self.ledger,
            stdin=io.StringIO(""),
            clock=self.clock,
            sleep=self.clock.sleep,
            notifier=notifier,
        )
        return code, out.getvalue(), err.getvalue()

    def test_timeout_never_sends_or_runs_then(self):
        seat = FakeSeat("dot", "Your dot", read=batch([msg("舊的", at="2026-10-01T01:00:00Z")]))
        code, text, err = self.invoke(
            [seat, unsupported_muse()],
            "wait", "dot", "--timeout", "20", "--poll", "5", "--then", "hand", "dot#last", "--to", "grok", "--yes", "接著",
        )
        self.assertEqual(code, 1)
        self.assertEqual(seat.send_calls, 0)
        self.assertEqual(seat.wait_calls, 0)
        self.assertIn("沒有重送", text)
        self.assertNotIn("接著", text)
        self.assertEqual(self.clock.sleeps, [5, 10, 5])
        self.assertNotIn("\a", err)
        self.assertEqual(self.ledger.records()[-1]["status"], "timed_out")
        self.assertEqual(self.ledger.records()[-1]["event"], "wait")

    def test_existing_reply_after_a_send_returns_without_resend(self):
        now = datetime.now(timezone.utc).isoformat()
        self.ledger.append({"event": "sent", "seat": "dot", "target": "Your dot", "nonce": "abc123", "sent_at": "2026-10-01T03:00:00+00:00", "at": now})
        sent = msg("hello\n\n[trinity abc123]", agent=False, at="2026-10-01T03:00:01Z", key="u1")
        reply = msg("新回覆", at="2026-10-01T03:05:00Z", key="a2")
        seat = FakeSeat("dot", "Your dot", read=batch([sent, reply]))
        code, text, _ = self.invoke([seat], "wait", "dot", "--timeout", "30", "--poll", "5")
        self.assertEqual(code, 0)
        self.assertEqual(seat.send_calls, 0)
        self.assertEqual(self.clock.sleeps, [])
        self.assertIn("新回覆", text)
        self.assertEqual(self.ledger.records()[-1]["status"], "seen")

    def test_notify_rings_and_does_not_include_the_reply_body(self):
        notes = []
        reply = msg("token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmYWtlIn0.c2ln", at="2026-10-01T03:05:00Z")
        self.ledger.append(
            {
                "event": "sent",
                "seat": "dot",
                "target": "Your dot",
                "nonce": "abc123",
                "sent_at": "2026-10-01T03:00:00+00:00",
                "at": "2026-10-01T03:00:00+00:00",
            }
        )
        sent = msg("q\n\n[trinity abc123]", agent=False, at="2026-10-01T03:00:01Z", key="u1")
        seat = FakeSeat("dot", "Your dot", read=batch([sent, reply]))
        code, text, err = self.invoke([seat], "wait", "dot", "--notify", notifier=lambda title, body: notes.append((title, body)))
        self.assertEqual(code, 0)
        self.assertIn("\a", err)
        self.assertEqual(notes[0][0], "trinity-cli")
        self.assertNotIn("eyJ", notes[0][1])
        self.assertNotIn("eyJ", text)
        self.assertEqual(seat.send_calls, 0)

    def test_then_hand_sends_only_after_a_reply_and_only_with_yes(self):
        sent = msg("q\n\n[trinity abc123]", agent=False, at="2026-10-01T03:00:01Z", key="u1")
        reply = msg("請轉交這句", at="2026-10-01T03:05:00Z", key="a2")
        self.ledger.append(
            {"event": "sent", "seat": "dot", "target": "Your dot", "nonce": "abc123", "sent_at": "2026-10-01T03:00:00+00:00", "at": "2026-10-01T03:00:00+00:00"}
        )
        origin = FakeSeat("dot", "Your dot", read=batch([sent, reply]))
        dest = FakeSeat(
            "grok",
            "Grok Bot",
            send=Result.ok(SendReceipt("Grok Bot/蝴蝶", "蝴蝶", "n", datetime.now(timezone.utc), "accepted")),
            wait=Result.ok(__import__("trinity_cli.model", fromlist=["WaitOutcome"]).WaitOutcome(True, None, True, 1)),
        )
        code, text, _ = self.invoke(
            [origin, dest],
            "wait", "dot", "--timeout", "5", "--then", "hand", "dot#last", "--to", "grok:蝴蝶", "接著做",
        )
        self.assertEqual(code, 2)
        self.assertEqual(dest.send_calls, 0)
        self.assertIn("沒有確認", text)
        self.ledger = Ledger(Path(self.tmp.name) / "ledger-again.jsonl")
        self.ledger.append(
            {"event": "sent", "seat": "dot", "target": "Your dot", "nonce": "abc123", "sent_at": "2026-10-01T03:00:00+00:00", "at": "2026-10-01T03:00:00+00:00"}
        )
        code, text, _ = self.invoke(
            [origin, dest],
            "wait", "dot", "--timeout", "5", "--then", "hand", "dot#last", "--to", "grok:蝴蝶", "--yes", "--timeout", "0", "接著做",
        )
        self.assertEqual(dest.send_calls, 1)
        self.assertIn("已轉交", text)
        self.assertIn("沒有重送", text)

    def test_unsupported_seat_does_not_fail(self):
        code, text, _ = self.invoke([unsupported_muse()], "wait", "muse", "--timeout", "0")
        self.assertEqual(code, 0)
        self.assertIn("不支援", text)
        self.assertEqual(self.ledger.records(), [])

    def test_json_timeout(self):
        seat = FakeSeat("dot", "Your dot", read=batch([]))
        out = io.StringIO()
        code = main(
            ["wait", "dot", "--timeout", "0", "--json"],
            seats=[seat],
            out=out,
            err=io.StringIO(),
            ledger=self.ledger,
            stdin=io.StringIO(""),
            clock=self.clock,
            sleep=self.clock.sleep,
        )
        self.assertEqual(code, 1)
        data = json.loads(out.getvalue())
        self.assertEqual(data["state"], "timed_out")
        self.assertFalse(data["sent"])
        self.assertEqual(seat.send_calls, 0)


if __name__ == "__main__":
    unittest.main()
