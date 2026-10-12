"""Offline Muse seat. These tests never start muse-web-cli or a browser."""

import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tests.fakes import FAKE_JWT, Clock, FakeRunner, MuseWorld
from trinity_cli import __version__
from trinity_cli.cli import main
from trinity_cli.config import resolve_muse_backend
from trinity_cli.seats.muse import MuseSeat, credential_mode_fix
from trinity_cli.state import Ledger, State
from trinity_cli.util import has_nonce

_STATES = (
    ("ok", "ok", None),
    ("browser_down", "failed", "muse-web-cli start --headless"),
    ("session_expired", "failed", "muse-web-cli login"),
    ("region_blocked", "failed", None),
    ("profile_busy", "failed", None),
    ("credential_permissions", "failed", "chmod 600 ~/.trinity-cli/muse-credential"),
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
        self.assertEqual(__version__, "0.4.6")

    def test_each_exit_state_on_status(self):
        for state, want, hint in _STATES:
            world = MuseWorld()
            world.force["status"] = state
            seat, runner = _seat(world)
            result = seat.status()
            self.assertEqual(result.state, want, state)
            if state == "credential_permissions":
                self.assertEqual(result.hint, credential_mode_fix(), state)
            elif hint:
                self.assertEqual(result.hint, hint, state)
            if state != "ok":
                self.assertNotIn("send", [call[0] for call in world.calls])
            self.assertTrue(all(argv[:3] == ["muse-web-cli", "--json", "--autostart"] for argv in _argv(runner)))
            self.assertNotIn("--wait", [part for argv in _argv(runner) for part in argv])

    def test_api_session_points_at_muse_login_not_the_browser(self):
        world = MuseWorld()
        world.backend = "api"
        world.force["status"] = "session_expired"
        seat, _ = _seat(world)
        result = seat.status()
        self.assertEqual(result.state, "failed")
        self.assertIn("trinity-cli login muse", result.hint)
        self.assertIn("muse-web-cli credential", result.hint)
        self.assertIn("mode 600", result.hint)
        self.assertIn("不印出", result.hint)
        self.assertNotIn("不讀", result.hint)
        self.assertNotIn("muse-web-cli login", result.hint)

    def test_api_backend_reports_each_unsupported_capability(self):
        world = MuseWorld(unsupported=True)
        world.backend = "api"
        seat, _ = _seat(world)
        results = {
            "status": seat.status(),
            "read": seat.read({}),
            "send": seat.send(None, "hi", "abc123"),
            "schedules": seat.schedules(),
            "memory": seat.memory(),
        }
        for name, result in results.items():
            self.assertEqual(result.state, "unsupported", name)
            self.assertTrue(result.error, name)

        mixed = MuseWorld()
        mixed.backend = "api"
        mixed.pending_count = None
        for command in ("messages", "send", "pending", "upcoming", "activity", "memory", "chats"):
            mixed.force[command] = "unsupported"
        seat, _ = _seat(mixed)
        status = seat.status()
        self.assertEqual(status.state, "ok")
        self.assertIn("api", status.value.summary)
        self.assertIn("chats 不支援", status.value.summary)
        self.assertEqual(seat.read({}).state, "unsupported")
        self.assertEqual(seat.send(None, "hi", "abc123").state, "unsupported")
        self.assertEqual(seat.schedules().state, "unsupported")
        self.assertEqual(seat.memory().state, "unsupported")

    def test_ok_status_skips_pending_until_there_is_something_to_do(self):
        world = MuseWorld()
        seat, _ = _seat(world)
        result = seat.status()
        self.assertEqual(result.state, "ok")
        self.assertEqual([call[0] for call in world.calls], ["status", "chats"])
        self.assertIn("背景", result.value.summary)
        self.assertIn("主聊天室", result.value.summary)
        self.assertEqual(result.value.details["chat"], "main")
        self.assertNotIn("SECRET_CHAT_TITLE", result.value.summary)
        self.assertEqual(result.value.waiting, [])

        world.pending_count = 2
        world.pending_items = [
            {"title": "核准行程", "detail": "明天", "time": "09:00"},
            {"title": "看一下記憶", "detail": "", "time": ""},
        ]
        world.calls.clear()
        result = seat.status()
        self.assertEqual([call[0] for call in world.calls], ["status", "pending", "chats"])
        self.assertEqual(result.value.waiting, ["等你處理：核准行程", "等你處理：看一下記憶"])

        world.pending_count = 0
        world.pending_items = []
        world.card = True
        world.headless = False
        world.calls.clear()
        result = seat.status()
        self.assertEqual([call[0] for call in world.calls], ["status", "chats"])
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
        self.assertEqual([call[0] for call in world.calls], ["upcoming", "activity"])
        self.assertFalse(seat.supports("instructions"))
        self.assertEqual(seat.instructions(update="do not write").state, "unsupported")
        self.assertEqual(len(runner.calls), 2)

    def test_upcoming_unsupported_does_not_fail_the_capability_as_an_exception(self):
        world = MuseWorld()
        world.force["upcoming"] = "unsupported"
        world.force["activity"] = "unsupported"
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
        self.assertEqual([call[0] for call in world.calls], ["chats", "send"])
        send = next(call for call in world.calls if call[0] == "send")
        self.assertTrue(has_nonce(send[-1], "abc123"))

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
        self.assertNotIn("SECRET_CHAT_TITLE", text)
        self.assertNotIn("SECRET_SIDE_TITLE", text)

    def test_who_can_suggest_a_live_muse(self):
        world = MuseWorld()
        seat, _ = _seat(world)
        out = io.StringIO()
        code = main(["who", "整理 muse 的記憶"], seats=[seat], out=out, err=io.StringIO())
        self.assertEqual(code, 0)
        self.assertIn("建議：Muse", out.getvalue())
        self.assertIn("不會送出", out.getvalue())
        self.assertEqual([call[0] for call in world.calls], ["status", "chats"])

    def test_side_chat_blocks_send(self):
        world = MuseWorld()
        world.chat = "side"
        seat, _ = _seat(world)
        result = seat.send(None, "你好", "abc123")
        self.assertEqual(result.state, "failed")
        self.assertIn("目前在副聊天室", result.error)
        self.assertIn("沒有送出", result.error)
        self.assertIn("主聊天室", result.hint)
        self.assertEqual([call[0] for call in world.calls], ["chats"])
        self.assertNotIn("SECRET_CHAT_TITLE", result.error)
        self.assertNotIn("SECRET_SIDE_TITLE", result.hint)

    def test_side_chat_read_does_not_advance_cursor(self):
        world = MuseWorld()
        world.chat = "side"
        world.messages = [{"role": "assistant", "text": "副聊天室內容", "presentation": False}]
        seat, _ = _seat(world)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        state = State(Path(tmp.name) / "state.json")
        kept = {"id": "keep", "keys": ["keep"]}
        state.save_cursors({"muse.messages": kept})
        out = io.StringIO()
        code = main(["digest"], seats=[seat], out=out, err=io.StringIO(), state=state)
        text = out.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("目前在副聊天室", text)
        self.assertIn("切回主聊天室", text)
        self.assertNotIn("副聊天室內容", text)
        self.assertNotIn("SECRET_SIDE_TITLE", text)
        self.assertEqual(state.cursors()["muse.messages"], kept)
        self.assertNotIn("messages", [call[0] for call in world.calls])
        self.assertNotIn("send", [call[0] for call in world.calls])

    def test_main_chat_still_sends(self):
        world = MuseWorld()
        seat, _ = _seat(world)
        result = seat.send(None, "你好", "abc123")
        self.assertEqual(result.state, "ok")
        self.assertEqual([call[0] for call in world.calls], ["chats", "send"])

    def test_unsupported_chats_falls_back_with_a_status_note(self):
        world = MuseWorld()
        world.chat = "unsupported"
        seat, _ = _seat(world)
        status = seat.status()
        self.assertEqual(status.state, "ok")
        self.assertIn("chats 不支援，仍使用目前開啟的對話", status.value.summary)
        self.assertEqual(status.value.details["chat"], "unknown")
        self.assertNotIn("SECRET_CHAT_TITLE", status.value.summary)
        world.calls.clear()
        sent = seat.send(None, "你好", "abc123")
        self.assertEqual(sent.state, "ok")
        self.assertEqual([call[0] for call in world.calls], ["chats", "send"])

    def test_missing_chat_panel_falls_back_with_a_status_note(self):
        world = MuseWorld()
        world.chat = "missing"
        seat, _ = _seat(world)
        status = seat.status()
        self.assertEqual(status.state, "ok")
        self.assertIn("切換面板不在，仍使用目前開啟的對話", status.value.summary)
        self.assertEqual(status.value.details["chat"], "unknown")
        world.calls.clear()
        sent = seat.send(None, "你好", "abc123")
        self.assertEqual(sent.state, "ok")
        self.assertEqual([call[0] for call in world.calls], ["chats", "send"])

    def test_closed_sidebar_falls_back_with_a_status_note(self):
        world = MuseWorld()
        world.chat = "sidebar_closed"
        seat, _ = _seat(world)
        status = seat.status()
        self.assertEqual(status.state, "ok")
        self.assertIn("Muse 側欄收起來", status.value.summary)
        self.assertEqual(status.value.details["chat"], "unknown")
        world.calls.clear()
        read = seat.read({})
        self.assertEqual(read.state, "ok")
        self.assertEqual([call[0] for call in world.calls][:2], ["chats", "messages"])
        world.calls.clear()
        sent = seat.send(None, "你好", "abc123")
        self.assertEqual(sent.state, "ok")
        self.assertEqual([call[0] for call in world.calls], ["chats", "send"])

    def test_status_shows_a_side_chat(self):
        world = MuseWorld()
        world.chat = "side"
        seat, _ = _seat(world)
        result = seat.status()
        self.assertEqual(result.state, "ok")
        self.assertIn("目前在副聊天室", result.value.summary)
        self.assertEqual(result.value.details["chat"], "side")
        self.assertEqual(result.value.hint, "在 Muse 視窗切回主聊天室後再讀、再送")
        self.assertIn("目前在副聊天室", result.value.problems)
        self.assertNotIn("SECRET_CHAT_TITLE", result.value.summary)
        self.assertNotIn("SECRET_SIDE_TITLE", result.value.hint)


class MuseBackendTests(unittest.TestCase):
    def test_precedence_is_flag_then_config_then_env(self):
        self.assertEqual(resolve_muse_backend("api", data={"muse_backend": "browser"}, env={"MUSE_WEB_BACKEND": "auto"}), "api")
        self.assertEqual(resolve_muse_backend(None, data={"muse_backend": "auto"}, env={"MUSE_WEB_BACKEND": "browser"}), "auto")
        self.assertEqual(resolve_muse_backend(None, data={}, env={"MUSE_WEB_BACKEND": "api"}), "api")
        self.assertIsNone(resolve_muse_backend(None, data={}, env={}))
        self.assertEqual(resolve_muse_backend("nope", data={"muse_backend": "api"}, env={}), "api")
        code = main(["status", "--muse-backend", "nope"], seats=[_seat(MuseWorld())[0]], out=io.StringIO(), err=io.StringIO())
        self.assertEqual(code, 2)

    def test_flag_passes_backend_and_status_names_it(self):
        world = MuseWorld()
        seat, _ = _seat(world)
        out = io.StringIO()
        code = main(["status", "--muse-backend", "api"], seats=[seat], out=out, err=io.StringIO())
        self.assertEqual(code, 0)
        self.assertIn("api", out.getvalue())
        self.assertTrue(world.used_backends)
        self.assertTrue(all(item == "api" for item in world.used_backends))
        self.assertEqual(seat.served_backend, "api")

    def test_auto_falls_back_per_capability_and_names_the_browser(self):
        world = MuseWorld()
        world.api_unsupported = {"status", "chats", "pending"}
        seat, _ = _seat(world)
        seat.backend = "auto"
        result = seat.status()
        self.assertEqual(result.state, "ok")
        self.assertTrue(result.value.details["fallback"])
        self.assertEqual(result.value.details["backend"], "browser")
        self.assertIn("已改走 browser", result.value.summary)
        self.assertEqual(world.used_backends[:2], ["api", "browser"])

    def test_auto_does_not_resend_after_a_timeout(self):
        world = MuseWorld()
        world.timeout_send = True
        seat, _ = _seat(world)
        seat.backend = "auto"
        result = seat.send(None, "hi", "abc123")
        self.assertEqual(result.state, "ok")
        self.assertEqual(world.used_backends, ["api", "api"])
        self.assertEqual([call[0] for call in world.calls], ["chats", "send"])
        self.assertEqual(sum(1 for call in world.calls if call[0] == "send"), 1)

    def test_auto_send_unsupported_may_fall_back_because_nothing_was_sent(self):
        world = MuseWorld()
        world.api_unsupported = {"send"}
        seat, _ = _seat(world)
        seat.backend = "auto"
        result = seat.send(None, "hi", "abc123")
        self.assertEqual(result.state, "ok")
        self.assertEqual([item for item, call in zip(world.used_backends, world.calls) if call[0] == "send"], ["api", "browser"])

    def test_activity_is_listed_beside_upcoming_and_a_card_is_not_a_reply(self):
        world = MuseWorld()
        world.activity_groups = [{"title": "今天", "items": [{"title": "晨間摘要", "detail": "", "time": "08:00"}]}]
        seat, _ = _seat(world)
        result = seat.schedules()
        self.assertEqual(result.state, "ok")
        self.assertEqual(result.value[-1].title, "晨間摘要")
        self.assertEqual(result.value[-1].status, "動態")
        world.messages = [
            {"role": "user", "text": "hi\n\n[trinity abc123]", "presentation": False},
            {"role": "assistant", "text": "卡片", "presentation": True},
        ]
        clock = Clock()
        seat, _ = _seat(world, clock)
        seat.backend = None
        from trinity_cli.model import SendReceipt
        from datetime import datetime, timezone

        receipt = SendReceipt("Muse", "Muse", "abc123", datetime.now(timezone.utc), "accepted")
        waited = seat.wait(receipt, timeout=0, poll=1)
        self.assertTrue(waited.value.timed_out)
        self.assertIsNone(waited.value.reply)

    def test_region_and_profile_have_fix_hints(self):
        for state, hint in (
            ("region_blocked", "不會繞過地區限制"),
            ("profile_busy", "muse-web-cli start --headless"),
            ("ui_changed", "更新 muse-web-cli"),
        ):
            world = MuseWorld()
            world.force["status"] = state
            seat, _ = _seat(world)
            result = seat.status()
            self.assertEqual(result.state, "failed")
            self.assertIn(hint, result.hint)


if __name__ == "__main__":
    unittest.main()
