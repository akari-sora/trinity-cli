import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tests.fakes import (
    BOT_ID,
    Clock,
    DotWorld,
    FakeRunner,
    FakeSeat,
    GrokWorld,
    dot_message,
    unsupported_muse,
    fail,
    grok_entry,
)
from trinity_cli.cli import main
from trinity_cli.model import Message, Result, SendReceipt, WaitOutcome
from trinity_cli.seats import DotSeat, GrokSeat
from trinity_cli.state import Ledger
from trinity_cli.util import has_nonce, nonce_tag


class AskTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / "ledger.jsonl")
        self.clock = Clock()

    def tearDown(self):
        self.tmp.cleanup()

    def ask(self, seats, *argv):
        out = io.StringIO()
        code = main(["ask", *argv], seats=seats, out=out, err=io.StringIO(), ledger=self.ledger, stdin=io.StringIO(""))
        return code, out.getvalue()

    def grok(self, world):
        return GrokSeat(FakeRunner(world), binary="/fake/bin/gbot", only_bots=[], clock=self.clock, sleep=self.clock.sleep)

    def dot(self, world):
        return DotSeat(FakeRunner(world), binary="chatgpt-dot-cli", hostnames=set(), clock=self.clock, sleep=self.clock.sleep)

    def events(self):
        return [r["event"] for r in self.ledger.records()]


class TimeoutNeverResendsTests(AskTestCase):
    def test_grok_send_timeout_reads_back_and_never_resends(self):
        world = GrokWorld()
        world.send_result = fail(1, "sendPrompt timed out after 15000ms; delivery is unknown. Do not resend automatically.")
        seat = self.grok(world)
        code, text = self.ask([seat], "grok", "蝴蝶", "status?", "--timeout", "30", "--poll", "10")
        self.assertEqual(code, 1)
        self.assertEqual(seat.runner.commands().count("send"), 1)
        self.assertEqual(len(world.sent), 1)
        self.assertIn("沒有重送", text)
        self.assertGreaterEqual(seat.runner.commands().count("thread"), 3)
        result = self.ledger.records()[-1]
        self.assertEqual(result["readback"], "not_seen")
        self.assertEqual(result["reply"], "timed_out")
        self.assertEqual(self.events(), ["sending", "sent", "result"])
        self.assertEqual(self.ledger.records()[1]["delivery"], "unknown")

    def test_grok_delivered_but_silent_times_out_without_resend(self):
        world = GrokWorld()
        seat = self.grok(world)
        code, text = self.ask([seat], "grok", "蝴蝶", "ping", "--timeout", "20", "--poll", "5")
        self.assertEqual(code, 1)
        self.assertEqual(seat.runner.commands().count("send"), 1)
        self.assertIn("⏱ 等了 20 秒沒有回覆，沒有重送", text)
        self.assertEqual(self.ledger.records()[-1]["readback"], "confirmed")

    def test_dot_timeout_never_resends(self):
        world = DotWorld()
        seat = self.dot(world)
        code, text = self.ask([seat], "dot", "ping", "--timeout", "30", "--poll", "10")
        self.assertEqual(code, 1)
        self.assertEqual(len(world.sent), 1)
        self.assertEqual(seat.runner.commands().count("send"), 1)
        self.assertEqual(self.ledger.records()[-1]["readback"], "confirmed")
        self.assertEqual(self.ledger.records()[-1]["reply"], "timed_out")

    def test_fake_seat_wait_timeout_never_calls_send_again(self):
        receipt = SendReceipt("Fake", "", "n", datetime.now(timezone.utc), "accepted")
        seat = FakeSeat("fake", "Fake", send=Result.ok(receipt), wait=Result.ok(WaitOutcome(True, None, True, 3)))
        code, _ = self.ask([seat], "all", "hello")
        self.assertEqual(code, 1)
        self.assertEqual(seat.send_calls, 1)
        self.assertEqual(seat.wait_calls, 1)


class AskFlowTests(AskTestCase):
    def test_ask_all_prints_replies_side_by_side(self):
        dot_world = DotWorld()
        grok_world = GrokWorld()
        dot_seat = self.dot(dot_world)
        grok_seat = self.grok(grok_world)

        original_dot = dot_world.__call__

        def dot_handler(args, stdin):
            proc = original_dot(args, stdin)
            if args[0] == "send":
                dot_world.messages.append(dot_message(999, "dot", "dot 的回答", "2026-10-01T03:01:00Z"))
            return proc

        original_grok = grok_world.__call__

        def grok_handler(args, stdin):
            proc = original_grok(args, stdin)
            if args[0] == "send":
                grok_world.transcripts[BOT_ID].append(grok_entry("r1", "assistant", "蝴蝶的回答"))
            return proc

        dot_seat.runner = FakeRunner(dot_handler)
        grok_seat.runner = FakeRunner(grok_handler)
        code, text = self.ask([dot_seat, grok_seat, unsupported_muse()], "all", "今天進度？", "--grok-bot", "蝴蝶")
        self.assertEqual(code, 0)
        self.assertIn("dot 的回答", text)
        self.assertIn("蝴蝶的回答", text)
        self.assertIn("不支援", text)
        self.assertIn(" │ ", text)
        self.assertEqual(len(dot_world.sent), 1)
        self.assertEqual(len(grok_world.sent), 1)
        self.assertEqual(dot_world.sent[0], grok_world.sent[0])

    def test_nonce_is_a_separate_last_line(self):
        world = GrokWorld()
        world.transcripts[BOT_ID] = []
        seat = self.grok(world)
        self.ask([seat], "grok", "蝴蝶", "  hello  ", "--timeout", "0")
        body = world.sent[0]
        self.assertEqual(body, body.strip())
        head, tag = body.rsplit("\n\n", 1)
        self.assertEqual(head, "hello")
        nonce = self.ledger.records()[0]["nonce"]
        self.assertEqual(tag, nonce_tag(nonce))
        self.assertTrue(has_nonce(body, nonce))

    def test_ledger_entry_exists_before_the_send_happens(self):
        seen = []

        def send(target, text, nonce):
            seen.extend(self.ledger.records())
            return Result.ok(SendReceipt("Fake", "", nonce, datetime.now(timezone.utc), "accepted"))

        reply = Message("Fake", "bot", "hi", None, True)
        seat = FakeSeat("fake", "Fake", send=send, wait=Result.ok(WaitOutcome(True, reply, False, 1)))
        code, _ = self.ask([seat], "all", "hello")
        self.assertEqual(code, 0)
        self.assertEqual(seen[0]["event"], "sending")
        final = self.ledger.records()[-1]
        for key in ("seat", "target", "nonce", "sent_at", "readback"):
            self.assertIn(key, final)
        self.assertEqual(final["readback"], "confirmed")

    def test_rejected_before_request_is_not_sent_and_not_polled(self):
        world = GrokWorld()
        seat = self.grok(world)
        code, text = self.ask([seat], "grok", "nobody", "hi")
        self.assertEqual(code, 1)
        self.assertIn("沒有送出", text)
        self.assertFalse(any("thread" in call["argv"] and "--help" not in call["argv"] for call in seat.runner.calls))
        self.assertEqual(self.events(), ["sending", "not_sent"])

    def test_grok_needs_a_bot_when_there_are_several(self):
        bots = [{"id": BOT_ID, "name": "蝴蝶", "kind": "bot"}, {"id": "b2", "name": "Two", "kind": "bot"}]
        world = GrokWorld(bots=bots)
        seat = self.grok(world)
        code, text = self.ask([seat, unsupported_muse()], "all", "hi")
        self.assertEqual(code, 1)
        self.assertEqual(world.sent, [])
        self.assertIn("ask grok <bot>", text)

    def test_ask_muse_is_unsupported_not_failed(self):
        code, text = self.ask([unsupported_muse()], "muse", "hi")
        self.assertEqual(code, 0)
        self.assertIn("不支援", text)
        self.assertEqual([row["event"] for row in self.ledger.records()], ["sending", "unsupported"])

    def test_json_output(self):
        receipt = SendReceipt("Fake", "", "n", datetime.now(timezone.utc), "accepted")
        seat = FakeSeat("fake", "Fake", send=Result.ok(receipt), wait=Result.ok(WaitOutcome(True, None, True, 3)))
        out = io.StringIO()
        main(["ask", "all", "hi", "--json"], seats=[seat], out=out, err=io.StringIO(), ledger=self.ledger)
        data = json.loads(out.getvalue())
        self.assertEqual(data["results"][0]["state"], "timed_out")
        self.assertEqual(data["results"][0]["readback"], "confirmed")

    def test_empty_text_is_rejected(self):
        code, _ = self.ask([unsupported_muse()], "all")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
