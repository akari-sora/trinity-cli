import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tests.fakes import (
    BOT_ID,
    BrokenOut,
    DotWorld,
    FakeRunner,
    FakeSeat,
    GrokWorld,
    dot_message,
    dot_record,
    fail,
    grok_entry,
    unsupported_muse,
)
from trinity_cli.cli import main
from trinity_cli.model import Batch, Message, ReadOutcome, Result
from trinity_cli.seats import DotSeat, GrokSeat
from trinity_cli.state import State


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def batch_seat(key="a", label="Alpha", items=None, cursor=None, gap=False):
    items = items if items is not None else [Message(label, "bot", "hello", at("2026-10-01T01:00:00"), True, "m1")]
    cursor = cursor if cursor is not None else {"id": items[-1].key if items else "m0"}
    return FakeSeat(key, label, read=Result.ok(ReadOutcome([Batch(f"{key}.messages", label, items, cursor, gap, "漏" if gap else "")])))


class DigestCursorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = State(Path(self.tmp.name) / "state.json")

    def tearDown(self):
        self.tmp.cleanup()

    def digest(self, seats, *argv, out=None):
        out = out if out is not None else io.StringIO()
        code = main(["digest", *argv], seats=seats, out=out, err=io.StringIO(), state=self.state)
        return code, out.getvalue() if not isinstance(out, BrokenOut) else ""

    def test_cursor_not_advanced_when_printing_fails(self):
        self.state.save_cursors({"a.messages": {"id": "m0"}})
        before = self.state.path.read_text(encoding="utf-8")
        code, _ = self.digest([batch_seat()], out=BrokenOut())
        self.assertEqual(code, 1)
        self.assertEqual(self.state.path.read_text(encoding="utf-8"), before)

    def test_cursor_not_created_when_printing_fails_first_time(self):
        code, _ = self.digest([batch_seat()], out=BrokenOut())
        self.assertEqual(code, 1)
        self.assertFalse(self.state.path.exists())

    def test_cursor_advanced_after_output_is_printed(self):
        code, text = self.digest([batch_seat()])
        self.assertEqual(code, 0)
        self.assertIn("hello", text)
        self.assertEqual(self.state.cursors()["a.messages"], {"id": "m1"})

    def test_peek_and_since_do_not_move_cursors(self):
        self.digest([batch_seat()], "--peek")
        self.assertFalse(self.state.path.exists())
        self.digest([batch_seat()], "--since", "2h")
        self.assertFalse(self.state.path.exists())

    def test_failed_source_is_loud_and_keeps_its_cursor(self):
        self.state.save_cursors({"b.messages": {"id": "old"}})
        bad = FakeSeat("b", "Beta", read=Result.failed("讀不到", "修好它"))
        code, text = self.digest([batch_seat(), bad, unsupported_muse()])
        self.assertEqual(code, 0)
        self.assertIn("✗ Beta 讀取失敗：讀不到 → 修好它（這不代表沒有新訊息）", text)
        self.assertIn("– Muse：不支援", text)
        self.assertEqual(self.state.cursors()["b.messages"], {"id": "old"})
        self.assertEqual(self.state.cursors()["a.messages"], {"id": "m1"})

    def test_failure_with_no_messages_never_says_nothing_new(self):
        bad = FakeSeat("b", "Beta", read=Result.failed("讀不到", "修好它"))
        empty = batch_seat(items=[], cursor={"id": "m0"})
        code, text = self.digest([empty, bad])
        self.assertEqual(code, 0)
        self.assertNotIn("沒有新訊息。", text)
        self.assertIn("失敗的來源請看上面", text)

    def test_unsupported_only_is_not_a_failure(self):
        code, text = self.digest([batch_seat(items=[], cursor={"id": "m0"}), unsupported_muse()])
        self.assertEqual(code, 0)
        self.assertIn("沒有新訊息。", text)

    def test_timeline_is_time_ordered_across_seats(self):
        a = batch_seat("a", "Alpha", [Message("Alpha", "bot", "second", at("2026-10-01T02:00:00"), True, "a2")])
        b = batch_seat("b", "Beta", [Message("Beta", "you", "first", at("2026-10-01T01:00:00"), False, "b1"),
                                     Message("Beta", "bot", "untimed", None, True, "b2")])
        code, text = self.digest([a, b])
        lines = [l for l in text.splitlines() if ": " in l]
        self.assertIn("first", lines[0])
        self.assertIn("second", lines[1])
        self.assertIn("untimed", lines[2])
        self.assertTrue(lines[2].startswith("時間不明"))

    def test_json_digest(self):
        out = io.StringIO()
        main(["--json", "digest"], seats=[batch_seat(gap=True)], out=out, err=io.StringIO(), state=self.state)
        data = json.loads(out.getvalue())
        self.assertEqual(data["items"][0]["text"], "hello")
        self.assertTrue(data["items"][0]["gap_before"])
        self.assertEqual(data["gaps"][0]["source"], "Alpha")


class DotReadTests(unittest.TestCase):
    def seat(self, world):
        return DotSeat(FakeRunner(world), binary="chatgpt-dot-cli", hostnames=set(), include_activity=False)

    def test_speaker_comes_from_account_ids_not_role(self):
        world = DotWorld(messages=[dot_message(1, "you", "question", "2026-10-01T01:00:00Z"),
                                   dot_message(2, "dot", "answer", "2026-10-01T01:01:00Z")])
        result = self.seat(world).read({})
        items = result.value.batches[0].items
        self.assertEqual([(m.speaker, m.text) for m in items], [("you", "question"), ("dot", "answer")])
        self.assertTrue(items[1].from_agent)

    def test_refuses_to_guess_speaker(self):
        world = DotWorld(messages=[dot_message(1, "dot", "x", "2026-10-01T01:00:00Z")],
                         dot=dot_record(with_dot_member=False))
        result = self.seat(world).read({})
        self.assertEqual(result.state, "failed")
        self.assertIn("無法從 JSON 判斷", result.error)

    def test_cursor_outside_full_window_is_a_gap(self):
        messages = [dot_message(i, "dot", f"m{i}", f"2026-10-01T01:0{i}:00Z") for i in range(1, 4)]
        world = DotWorld(messages=messages)
        cursor = {"dot.messages": {"id": "msg_gone", "at": "2026-09-30T00:00:00Z"}}
        result = self.seat(world).read(cursor, limit=3)
        batch = result.value.batches[0]
        self.assertTrue(batch.gap)
        self.assertEqual(len(batch.items), 3)

    def test_no_gap_when_whole_history_fits(self):
        messages = [dot_message(i, "dot", f"m{i}", f"2026-10-01T01:0{i}:00Z") for i in range(1, 3)]
        world = DotWorld(messages=messages)
        cursor = {"dot.messages": {"id": "msg_gone", "at": "2026-09-30T00:00:00Z"}}
        batch = self.seat(world).read(cursor, limit=3).value.batches[0]
        self.assertFalse(batch.gap)

    def test_only_new_messages_after_cursor(self):
        messages = [dot_message(i, "dot", f"m{i}", f"2026-10-01T01:0{i}:00Z") for i in range(1, 4)]
        world = DotWorld(messages=messages)
        batch = self.seat(world).read({"dot.messages": {"id": "msg_fake00000002"}}).value.batches[0]
        self.assertEqual([m.text for m in batch.items], ["m3"])
        self.assertEqual(batch.new_cursor["id"], "msg_fake00000003")

    def test_limit_is_capped_below_the_api_422(self):
        world = DotWorld()
        seat = self.seat(world)
        seat.read({}, limit=50)
        argv = next(c["argv"] for c in seat.runner.calls if "messages" in c["argv"])
        self.assertEqual(argv[argv.index("--limit") + 1], "32")

    def test_messages_failure_is_a_source_failure(self):
        world = DotWorld()
        world.overrides["messages"] = fail(3, "GET /tbo/{id}/messages 500 upstream")
        result = self.seat(world).read({})
        self.assertEqual(result.state, "ok")
        self.assertIn("500", result.value.failures[0].error)
        self.assertNotIn("登入", result.value.failures[0].error)

    def test_v021_object_shape_empty_room_and_no_positional_id(self):
        world = DotWorld()
        seat = DotSeat(FakeRunner(world), binary="chatgpt-dot-cli", dot_id="tbo_fakeDot0001abc", hostnames=set())
        result = seat.read({})
        self.assertEqual(result.state, "ok")
        self.assertEqual(result.value.batches[0].items, [])
        argv = next(call["argv"] for call in seat.runner.calls if "messages" in call["argv"])
        self.assertEqual(argv, ["chatgpt-dot-cli", "--json", "messages", "--limit", "30", "--dot-id", "tbo_fakeDot0001abc"])

    def test_usage_exit_is_not_a_login_failure(self):
        world = DotWorld()
        world.overrides["messages"] = fail(2, "limit must be an integer from 1 to 32")
        result = self.seat(world).read({})
        self.assertIn("limit", result.value.failures[0].error)
        self.assertNotIn("登入檔", result.value.failures[0].error)


class GrokReadTests(unittest.TestCase):
    def seat(self, world):
        return GrokSeat(FakeRunner(world), binary="/fake/bin/gbot", only_bots=[])

    def test_fallback_marks_gap_reset_when_cursor_is_gone(self):
        world = GrokWorld(transcripts={BOT_ID: [grok_entry("e5", "assistant", "new")]})
        batch = self.seat(world).read({f"grok.{BOT_ID}": {"id": "e1"}}).value.batches[0]
        self.assertTrue(batch.gap)
        self.assertEqual([m.text for m in batch.items], ["new"])
        self.assertEqual(batch.new_cursor, {"id": "e5"})

    def test_fallback_returns_only_entries_after_cursor(self):
        world = GrokWorld(transcripts={BOT_ID: [grok_entry("e1", "user", "q"), grok_entry("e2", "assistant", "a")]})
        batch = self.seat(world).read({f"grok.{BOT_ID}": {"id": "e1"}}).value.batches[0]
        self.assertFalse(batch.gap)
        self.assertEqual([(m.speaker, m.text) for m in batch.items], [("蝴蝶", "a")])

    def test_uses_after_when_gbot_supports_it(self):
        world = GrokWorld(transcripts={BOT_ID: [grok_entry("e1", "user", "q"), grok_entry("e2", "assistant", "a")]},
                          supports_after=True)
        seat = self.seat(world)
        batch = seat.read({f"grok.{BOT_ID}": {"id": "e1"}}).value.batches[0]
        thread_argv = next(c["argv"] for c in seat.runner.calls if "thread" in c["argv"] and "--help" not in c["argv"])
        self.assertIn("--after", thread_argv)
        self.assertEqual([m.text for m in batch.items], ["a"])
        self.assertEqual(batch.new_cursor, {"id": "e2"})

    def test_after_gap_reset_is_marked(self):
        world = GrokWorld(transcripts={BOT_ID: [grok_entry("e9", "assistant", "late")]}, supports_after=True)
        batch = self.seat(world).read({f"grok.{BOT_ID}": {"id": "e1"}}).value.batches[0]
        self.assertTrue(batch.gap)

    def test_gap_shows_as_possibly_missed_in_digest(self):
        world = GrokWorld(transcripts={BOT_ID: [grok_entry("e5", "assistant", "new")]})
        with tempfile.TemporaryDirectory() as tmp:
            state = State(Path(tmp) / "state.json")
            state.save_cursors({f"grok.{BOT_ID}": {"id": "e1"}})
            out = io.StringIO()
            main(["digest"], seats=[self.seat(world)], out=out, err=io.StringIO(), state=state)
        self.assertIn("可能漏看", out.getvalue())
        self.assertNotIn(BOT_ID, out.getvalue())

    def test_one_bot_failing_does_not_hide_the_others(self):
        bots = [{"id": BOT_ID, "name": "蝴蝶", "kind": "bot"}, {"id": "b-two", "name": "Two", "kind": "bot"}]
        world = GrokWorld(transcripts={BOT_ID: [grok_entry("e1", "assistant", "ok")]}, bots=bots)
        original = world.__call__

        def handler(args, stdin):
            if args[:2] == ["thread", "b-two"]:
                return fail(1, "gateway 503")
            return original(args, stdin)

        seat = GrokSeat(FakeRunner(handler), binary="/fake/bin/gbot", only_bots=[])
        outcome = seat.read({}).value
        self.assertEqual(len(outcome.batches), 1)
        self.assertEqual(outcome.failures[0].label, "Grok Bot/Two")


if __name__ == "__main__":
    unittest.main()
