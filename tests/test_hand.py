import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tests.fakes import FAKE_JWT, Clock, DotWorld, FakeRunner, FakeSeat, GrokWorld, MuseWorld, dot_message, unsupported_muse
from trinity_cli.cli import main
from trinity_cli.model import OK, Batch, Message, ReadOutcome, Result, SendReceipt, WaitOutcome
from trinity_cli.seats import DotSeat, GrokSeat, MuseSeat
from trinity_cli.state import Ledger, State
from trinity_cli.util import has_nonce


def messages(*rows):
    return Result.ok(ReadOutcome([Batch("dot.messages", "Your dot", list(rows), None)]))


def agent(text, at="2026-10-01T03:00:00Z", key="m1"):
    return Message("Your dot", "dot", text, datetime.fromisoformat(at.replace("Z", "+00:00")), True, key)


class HandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / "ledger.jsonl")
        self.state = State(Path(self.tmp.name) / "state.json")
        self.old_home = os.environ.get("TRINITY_HOME")
        os.environ["TRINITY_HOME"] = self.tmp.name

    def tearDown(self):
        if self.old_home is None:
            os.environ.pop("TRINITY_HOME", None)
        else:
            os.environ["TRINITY_HOME"] = self.old_home
        self.tmp.cleanup()

    def invoke(self, seats, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = main(list(argv), seats=seats, out=out, err=err, ledger=self.ledger, state=self.state, stdin=io.StringIO(""))
        return code, out.getvalue(), err.getvalue()

    def test_confirmation_is_required_without_yes(self):
        dest = FakeSeat("grok", "Grok Bot", send=Result.ok(SendReceipt("Grok Bot/蝴蝶", "蝴蝶", "n", datetime.now(timezone.utc), "accepted")))
        code, text, _ = self.invoke(
            [FakeSeat("dot", "Your dot", read=messages(agent("來源回覆"))), dest, unsupported_muse()],
            "hand", "dot#last", "--to", "grok:蝴蝶", "請看這則",
        )
        self.assertEqual(code, 2)
        self.assertEqual(dest.send_calls, 0)
        self.assertIn("請看這則", text)
        self.assertIn("來源回覆", text)
        self.assertIn("轉自", text)
        self.assertIn("沒有確認，沒有送出", text)
        self.assertEqual(self.ledger.records(), [])
        self.assertFalse(self.state.path.exists())

    def test_yes_sends_once_and_ledgers_readback(self):
        captured = []
        seen = []

        def send(target, text, nonce):
            captured.append(text)
            seen.extend(self.ledger.records())
            return Result.ok(SendReceipt("Grok Bot/蝴蝶", "蝴蝶", nonce, datetime.now(timezone.utc), "accepted"))

        reply = Message("Grok Bot/蝴蝶", "蝴蝶", "收到", datetime.now(timezone.utc), True, "r1")
        dest = FakeSeat(
            "grok",
            "Grok Bot",
            send=send,
            wait=Result.ok(WaitOutcome(True, reply, False, 1)),
        )
        code, text, _ = self.invoke(
            [FakeSeat("dot", "Your dot", read=messages(agent("來源回覆"))), dest],
            "hand", "dot#last", "--to", "grok:蝴蝶", "--yes", "請看這則",
        )
        self.assertEqual(code, 0)
        self.assertEqual(dest.send_calls, 1)
        self.assertEqual(dest.wait_calls, 1)
        self.assertIn("請看這則", captured[0])
        self.assertIn("來源回覆", captured[0])
        self.assertIn("轉自", captured[0])
        self.assertEqual(seen[0]["event"], "sending")
        self.assertEqual(seen[0]["kind"], "hand")
        self.assertNotIn("來源回覆", json.dumps(self.ledger.records()))
        events = [row["event"] for row in self.ledger.records()]
        self.assertEqual(events, ["sending", "sent", "result"])
        self.assertEqual(self.ledger.records()[-1]["readback"], "confirmed")
        self.assertEqual(self.ledger.records()[-1]["reply"], "replied")
        self.assertIn("收到", text)

    def test_timeout_does_not_resend(self):
        dest = FakeSeat(
            "grok",
            "Grok Bot",
            send=Result.ok(SendReceipt("Grok Bot/蝴蝶", "蝴蝶", "n", datetime.now(timezone.utc), "accepted")),
            wait=Result.ok(WaitOutcome(True, None, True, 2)),
        )
        code, text, _ = self.invoke(
            [FakeSeat("dot", "Your dot", read=messages(agent("來源回覆"))), dest],
            "hand", "dot#last", "--to", "grok", "--yes", "--timeout", "0", "請看",
        )
        self.assertEqual(code, 1)
        self.assertEqual(dest.send_calls, 1)
        self.assertIn("沒有重送", text)

    def test_unsupported_muse_send_does_not_wait_or_resend(self):
        origin = FakeSeat("dot", "Your dot", read=messages(agent("來源回覆")))
        world = MuseWorld(unsupported=True)
        muse = MuseSeat(FakeRunner(world), binary="muse-web-cli")
        code, text, _ = self.invoke([origin, muse], "hand", "dot#last", "--to", "muse", "--yes", "請看")
        self.assertEqual(code, 0)
        self.assertIn("不支援", text)
        self.assertEqual(origin.send_calls, 0)
        self.assertEqual([call[0] for call in world.calls], ["send"])
        self.assertNotIn("--wait", [part for call in muse.runner.calls for part in call["argv"]])
        self.assertEqual([row["event"] for row in self.ledger.records()], ["sending", "unsupported"])

    def test_real_seats_append_nonce_and_do_not_move_cursors(self):
        self.state.save_cursors({"dot.messages": {"id": "keep-me", "at": "2026-10-01T00:00:00+00:00"}})
        dot_world = DotWorld(messages=[dot_message(1, "dot", "dot 的原話", "2026-10-01T02:00:00Z")])
        grok_world = GrokWorld()
        clock = Clock()
        dot = DotSeat(FakeRunner(dot_world), binary="chatgpt-dot-cli", hostnames=set(), clock=clock, sleep=clock.sleep)
        grok = GrokSeat(FakeRunner(grok_world), binary="/fake/bin/gbot", only_bots=[], clock=clock, sleep=clock.sleep)
        code, text, _ = self.invoke([dot, grok, unsupported_muse()], "hand", "dot#last", "--to", "grok:蝴蝶", "--yes", "--timeout", "0", "請處理")
        self.assertEqual(code, 1)
        self.assertEqual(len(grok_world.sent), 1)
        self.assertEqual(dot.runner.commands().count("send"), 0)
        body = grok_world.sent[0]
        self.assertIn("請處理", body)
        self.assertIn("轉自", body)
        self.assertIn("dot 的原話", body)
        nonce = self.ledger.records()[0]["nonce"]
        self.assertTrue(has_nonce(body, nonce))
        self.assertEqual(self.state.cursors()["dot.messages"]["id"], "keep-me")
        self.assertNotIn(FAKE_JWT, text)

    def test_second_newest_reply_can_be_chosen(self):
        older = agent("較舊", "2026-10-01T01:00:00Z", "m1")
        newer = agent("較新", "2026-10-01T02:00:00Z", "m2")
        captured = []

        def send(target, text, nonce):
            captured.append(text)
            return Result.ok(SendReceipt("Grok", "蝴蝶", nonce, datetime.now(timezone.utc), "accepted"))

        dest = FakeSeat("grok", "Grok Bot", send=send, wait=Result.ok(WaitOutcome(False, None, True, 1)))
        self.invoke([FakeSeat("dot", "Your dot", read=messages(older, newer)), dest], "hand", "dot#2", "--to", "grok", "--yes", "--timeout", "0", "看舊的")
        self.assertIn("較舊", captured[0])
        self.assertNotIn("較新", captured[0])

    def test_json_without_yes_does_not_send(self):
        dest = FakeSeat("grok", "Grok Bot")
        out = io.StringIO()
        code = main(
            ["--json", "hand", "dot#last", "--to", "grok", "請看"],
            seats=[FakeSeat("dot", "Your dot", read=messages(agent(f"secret {FAKE_JWT}"))), dest],
            out=out,
            err=io.StringIO(),
            ledger=self.ledger,
            stdin=io.StringIO(""),
        )
        self.assertEqual(code, 2)
        self.assertEqual(dest.send_calls, 0)
        data = json.loads(out.getvalue())
        self.assertFalse(data["confirmed"])
        self.assertFalse(data["sent"])
        self.assertNotIn(FAKE_JWT, out.getvalue())


if __name__ == "__main__":
    unittest.main()
