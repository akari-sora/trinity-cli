"""Offline Muse seat. These tests never start muse-web-cli or a browser."""

import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tests.fakes import FAKE_JWT, Clock, FakeRunner, MuseWorld
from trinity_cli import __version__
from trinity_cli.cli import main
from trinity_cli.seats.muse import MuseSeat
from trinity_cli.state import Ledger, State
from trinity_cli.util import has_nonce

_STATES = (
    ("ok", "ok", None),
    ("browser_down", "failed", "muse-web-cli start --headless"),
    ("session_expired", "failed", "muse-web-cli login"),
    ("region_blocked", "failed", None),
    ("profile_busy", "failed", None),
    ("credential_permissions", "failed", None),
    ("ui_changed", "failed", None),
    ("timeout", "failed", None),
    ("unsupported", "unsupported", None),
)


def _seat(world, clock=None):
    clock = clock or Clock()
    runner = FakeRunner(world)
    seat = MuseSeat(runner, binary="muse-web-cli", clock=clock, sleep=clock.sleep)
    return seat, runner


def _argv(runner):
    return [call["argv"] for call in runner.calls]


class MuseContractTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(__version__, "0.3.0")

    def test_each_exit_state_on_status(self):
        for state, want, hint in _STATES:
            world = MuseWorld()
            world.force["status"] = state
            seat, runner = _seat(world)
            result = seat.status()
            self.assertEqual(result.state, want, state)
            if hint:
                self.assertEqual(result.hint, hint, state)
            if state != "ok":
                self.assertNotIn("send", [call[0] for call in world.calls])
            self.assertTrue(all(argv[:3] == ["muse-web-cli", "--json", "--autostart"] for argv in _argv(runner)))
            self.assertNotIn("--wait", [part for argv in _argv(runner) for part in argv])

    def test_ok_status_skips_pending_until_there_is_something_to_do(self):
        world = MuseWorld()
        seat, _ = _seat(world)
        result = seat.status()
        self.assertEqual(result.state, "ok")
        self.assertEqual([call[0] for call in world.calls], ["status"])
        self.assertIn("背景", result.value.summary)
        self.assertEqual(result.value.waiting, [])

        world.pending_count = 2
        world.pending_items = [
            {"title": "核准行程", "detail": "明天", "time": "09:00"},
            {"title": "看一下記憶", "detail": "", "time": ""},
        ]
        world.calls.clear()
        result = seat.status()
        self.assertEqual([call[0] for call in world.calls], ["status", "pending"])
        self.assertEqual(result.value.waiting, ["等你處理：核准行程", "等你處理：看一下記憶"])

        world.pending_count = 0
        world.pending_items = []
        world.card = True
        world.headless = False
        world.calls.clear()
        result = seat.status()
        self.assertEqual([call[0] for call in world.calls], ["status"])
        self.assertIn("有視窗", result.value.summary)
        self.assertEqual(result.value.waiting, ["等你處理：最新回覆是卡片"])

    def test_missing_binary_does_not_spawn(self):
        seat = MuseSeat(FakeRunner(MuseWorld()), binary="")
        result = seat.status()
        self.assertEqual(result.state, "failed")
        self.assertIn("找不到 muse-web-cli", result.error)
        self.assertEqual(result.hint, "安裝 muse-web-cli，或用 TRINITY_MUSE_CLI 指定路徑")
        self.assertEqual(seat.runner.calls, [])

    def test_schedules_come_from_upcoming_and_instructions_are_unsupported(self):
        world = MuseWorld()
        world.groups = [{"title": "明天", "items": [{"name": "晨間摘要", "time": "08:00"}]}]
        seat, runner = _seat(world)
        result = seat.schedules()
        self.assertEqual(result.state, "ok")
        self.assertEqual(result.value[0].title, "晨間摘要")
        self.assertEqual(result.value[0].when, "08:00")
        self.assertEqual([call[0] for call in world.calls], ["upcoming"])
        self.assertFalse(seat.supports("instructions"))
        self.assertEqual(seat.instructions(update="do not write").state, "unsupported")
        self.assertEqual(len(runner.calls), 1)

    def test_upcoming_unsupported_does_not_fail_the_capability_as_an_exception(self):
        world = MuseWorld()
        world.force["upcoming"] = "unsupported"
        seat, _ = _seat(world)
        result = seat.schedules()
        self.assertEqual(result.state, "unsupported")
        self.assertIn("不支援", result.error)

    def test_digest_seen_set_and_gap(self):
        world = MuseWorld()
        world.messages = [
            {"role": "user", "text": "第一則", "presentation": False},
            {"role": "assistant", "text": "第二則", "presentation": False},
        ]
        seat, _ = _seat(world)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        state = State(Path(tmp.name) / "state.json")
        out = io.StringIO()
        code = main(["digest"], seats=[seat], out=out, err=io.StringIO(), state=state)
        text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("第一則", text)
        self.assertIn("第二則", text)
        self.assertNotIn("可能漏看", text)
        cursor = state.cursors()["muse.messages"]
        self.assertIn("id", cursor)
        self.assertEqual(len(cursor["keys"]), 2)

        out = io.StringIO()
        code = main(["digest"], seats=[seat], out=out, err=io.StringIO(), state=state)
        self.assertEqual(code, 0)
        self.assertIn("沒有新訊息。", out.getvalue())
        self.assertNotIn("可能漏看", out.getvalue())

        world.messages = [
            {"role": "user", "text": "新的一則", "presentation": False},
            {"role": "assistant", "text": "新的回覆", "presentation": False},
        ]
        out = io.StringIO()
        code = main(["digest"], seats=[seat], out=out, err=io.StringIO(), state=state)
        text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("可能漏看", text)
        self.assertIn("新的回覆", text)
        self.assertNotIn("第一則", text)

    def test_first_read_is_capped_and_since_cannot_filter_untimed_messages(self):
        world = MuseWorld()
        world.messages = [{"role": "assistant", "text": f"m{i}", "presentation": False} for i in range(12)]
        seat, _ = _seat(world)
        result = seat.read({})
        batch = result.value.batches[0]
        self.assertEqual([item.text for item in batch.items], [f"m{i}" for i in range(2, 12)])
        self.assertIn("第一次讀取", batch.note)
        self.assertFalse(batch.gap)
        looked = seat.read({}, since=datetime(2026, 10, 1, tzinfo=timezone.utc))
        note = looked.value.batches[0]
        self.assertEqual(len(note.items), 12)
        self.assertIn("沒有時間戳", note.note)
        self.assertFalse(note.gap)

    def test_send_does_not_wait_and_a_reply_is_polled(self):
        world = MuseWorld()
        world.reply = "這是回覆"
        seat, runner = _seat(world)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = io.StringIO()
        code = main(
            ["ask", "muse", "你好", "--timeout", "5"],
            seats=[seat],
            out=out,
            err=io.StringIO(),
            ledger=Ledger(Path(tmp.name) / "ledger.jsonl"),
        )
        text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("這是回覆", text)
        sends = [argv for argv in _argv(runner) if "send" in argv]
        self.assertEqual(len(sends), 1)
        self.assertNotIn("--wait", sends[0])
        self.assertEqual(sends[0][:4], ["muse-web-cli", "--json", "--autostart", "send"])
        self.assertIn("--", sends[0])
        body = sends[0][-1]
        self.assertTrue(body.startswith("你好\n\n[trinity "))
        self.assertIn("messages", [call[0] for call in world.calls])
        self.assertEqual([call[0] for call in world.calls].count("send"), 1)

    def test_subprocess_timeout_never_resends(self):
        world = MuseWorld()
        world.timeout_send = True
        seat, runner = _seat(world)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = io.StringIO()
        code = main(
            ["ask", "muse", "你好", "--timeout", "0"],
            seats=[seat],
            out=out,
            err=io.StringIO(),
            ledger=Ledger(Path(tmp.name) / "ledger.jsonl"),
        )
        self.assertEqual(code, 1)
        self.assertIn("沒有重送", out.getvalue())
        self.assertEqual([call[0] for call in world.calls].count("send"), 1)
        self.assertNotIn("--wait", [part for argv in _argv(runner) for part in argv])

    def test_page_timeout_after_an_attempt_never_resends(self):
        world = MuseWorld()
        world.force["send"] = "timeout"
        seat, _ = _seat(world)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = io.StringIO()
        code = main(
            ["ask", "muse", "你好", "--timeout", "0"],
            seats=[seat],
            out=out,
            err=io.StringIO(),
            ledger=Ledger(Path(tmp.name) / "ledger.jsonl"),
        )
        self.assertEqual(code, 1)
        self.assertIn("沒有重送", out.getvalue())
        self.assertEqual([call[0] for call in world.calls].count("send"), 1)
        self.assertIn("messages", [call[0] for call in world.calls])

    def test_setup_failure_does_not_send(self):
        world = MuseWorld()
        world.force["send"] = "session_expired"
        seat, _ = _seat(world)
        result = seat.send(None, "你好", "abc123")
        self.assertEqual(result.state, "failed")
        self.assertIn("沒有送出", result.error)
        self.assertEqual(result.hint, "muse-web-cli login")
        self.assertEqual([call[0] for call in world.calls], ["send"])
        self.assertTrue(has_nonce(world.calls[0][-1], "abc123"))

    def test_memory_is_read_only_on_brief_diff_and_push_stays_a_draft(self):
        world = MuseWorld()
        world.memory_text = "舊的記憶"
        seat, _ = _seat(world)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "brief.md"
        path.write_text("新的說明\n", encoding="utf-8")
        out = io.StringIO()
        code = main(["brief", "diff"], seats=[seat], out=out, err=io.StringIO(), brief_path=path)
        text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("舊的記憶", text)
        self.assertIn("新的說明", text)
        self.assertIn("沒有指令 API", text)
        self.assertEqual([call[0] for call in world.calls], ["memory"])

        world.calls.clear()
        out = io.StringIO()
        code = main(
            ["brief", "push", "--yes"],
            seats=[seat],
            out=out,
            err=io.StringIO(),
            brief_path=path,
            ledger=Ledger(Path(tmp.name) / "ledger.jsonl"),
            stdin=io.StringIO(""),
        )
        self.assertEqual(code, 0)
        self.assertIn("沒有送出", out.getvalue())
        self.assertEqual(world.calls, [])

    def test_printed_output_has_no_token_like_strings(self):
        world = MuseWorld()
        world.pending_count = 1
        world.pending_items = [{"title": FAKE_JWT, "detail": "leave this", "time": "1:00"}]
        world.messages = [{"role": "assistant", "text": "普通回覆", "presentation": False, "secret": FAKE_JWT}]
        seat, _ = _seat(world)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        state = State(Path(tmp.name) / "state.json")
        out = io.StringIO()
        main(["status"], seats=[seat], out=out, err=io.StringIO(), state=state)
        main(["digest"], seats=[seat], out=out, err=io.StringIO(), state=state)
        text = out.getvalue()
        self.assertIn("等你處理", text)
        self.assertIn("普通回覆", text)
        self.assertNotIn(FAKE_JWT, text)
        self.assertNotIn("eyJ", text)

    def test_who_can_suggest_a_live_muse(self):
        world = MuseWorld()
        seat, _ = _seat(world)
        out = io.StringIO()
        code = main(["who", "整理 muse 的記憶"], seats=[seat], out=out, err=io.StringIO())
        self.assertEqual(code, 0)
        self.assertIn("建議：Muse", out.getvalue())
        self.assertIn("不會送出", out.getvalue())
        self.assertEqual([call[0] for call in world.calls], ["status"])


if __name__ == "__main__":
    unittest.main()
