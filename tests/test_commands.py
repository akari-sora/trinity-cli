import io
import json
import tempfile
import unittest
from pathlib import Path

from tests.fakes import DotWorld, FakeRunner, FakeSeat, GrokWorld, fail, unsupported_muse
from trinity_cli.cli import main
from trinity_cli.model import Result, ScheduleItem, SeatStatus
from trinity_cli.seats import DotSeat, GrokSeat
from trinity_cli.seats.base import Seat


class SchedulingSeat(Seat):
    family = "grok"
    key = "grok"
    label = "Grok Bot"

    def __init__(self, items):
        self._items = items

    def schedules(self):
        return Result.ok(self._items)


def run(seats, *argv, **kwargs):
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), seats=seats, out=out, err=err, stdin=io.StringIO(""), **kwargs)
    return code, out.getvalue(), err.getvalue()


class ScheduleCommandTests(unittest.TestCase):
    def test_unsupported_does_not_fail_and_duplicates_are_flagged(self):
        world = DotWorld()
        world.automations = [{"title": "晨間摘要", "schedule": "0 8 * * *", "status": "ACTIVE"}]
        dot = DotSeat(FakeRunner(world), binary="chatgpt-dot-cli", hostnames=set())
        grok = SchedulingSeat([ScheduleItem("晨間摘要", "0 8 * * *", "enabled")])
        code, text, _ = run([dot, grok, unsupported_muse()], "schedules")
        self.assertEqual(code, 0)
        self.assertIn("晨間摘要", text)
        self.assertIn("不支援", text)
        self.assertIn("可能重複", text)
        self.assertIn("標題和時間都一樣", text)
        self.assertNotIn("✗", text)

    def test_a_failing_seat_is_visible_and_others_remain(self):
        world = DotWorld()
        world.overrides["automations"] = fail(3, "automations down")
        dot = DotSeat(FakeRunner(world), binary="chatgpt-dot-cli", hostnames=set())
        code, text, _ = run([dot, unsupported_muse()], "schedules")
        self.assertEqual(code, 1)
        self.assertIn("✗", text)
        self.assertIn("Muse", text)
        self.assertIn("不支援", text)

    def test_grok_without_a_schedules_command_is_unsupported(self):
        grok = GrokSeat(FakeRunner(GrokWorld()), binary="/fake/bin/gbot", only_bots=[])
        code, text, _ = run([grok], "schedules")
        self.assertEqual(code, 0)
        self.assertIn("沒有排程", text)

    def test_json(self):
        code, text, _ = run([unsupported_muse()], "--json", "schedules")
        self.assertEqual(code, 0)
        data = json.loads(text)
        self.assertEqual(data["seats"][0]["state"], "unsupported")
        self.assertEqual(data["duplicates"], [])


class WhoTests(unittest.TestCase):
    def test_suggests_dot_for_local_files_when_the_mac_is_connected(self):
        dot = FakeSeat(
            "dot",
            "Your dot",
            status=Result.ok(SeatStatus("運作中", details={"paused": False, "this_mac_attached": True, "quota_used_percent": 20})),
        )
        grok = FakeSeat("grok", "Grok Bot", status=Result.ok(SeatStatus("連線正常")))
        code, text, _ = run([dot, grok, unsupported_muse()], "who", "整理這台 Mac 的下載資料夾")
        self.assertEqual(code, 0)
        self.assertIn("建議：Your dot", text)
        self.assertIn("這台 Mac 已連接", text)
        self.assertIn("不會送出", text)
        self.assertEqual(dot.send_calls, 0)
        self.assertEqual(grok.send_calls, 0)

    def test_suggests_grok_for_translation_and_warns_about_a_paused_dot(self):
        dot = FakeSeat("dot", "Your dot", status=Result.ok(SeatStatus("已暫停", details={"paused": True})))
        grok = FakeSeat("grok", "Grok Bot", status=Result.ok(SeatStatus("連線正常")))
        code, text, _ = run([dot, grok, unsupported_muse()], "who", "翻譯這段")
        self.assertEqual(code, 0)
        self.assertIn("建議：Grok Bot", text)
        self.assertIn("已暫停", text)
        self.assertIn("不支援", text)

    def test_a_failed_status_does_not_fail_the_advice(self):
        dot = FakeSeat("dot", "Your dot", status=Result.failed("連不上", "codex login"))
        grok = FakeSeat("grok", "Grok Bot", status=Result.ok(SeatStatus("連線正常")))
        code, text, _ = run([dot, grok], "who", "翻譯一段說明")
        self.assertEqual(code, 0)
        self.assertIn("建議：Grok Bot", text)
        self.assertIn("狀態讀不到", text)

    def test_tie_is_not_a_decision(self):
        dot = FakeSeat("dot", "Your dot", status=Result.ok(SeatStatus("運作中")))
        grok = FakeSeat("grok", "Grok Bot", status=Result.ok(SeatStatus("連線正常")))
        code, text, _ = run([dot, grok, unsupported_muse()], "who", "你好")
        self.assertEqual(code, 0)
        self.assertIn("沒有明顯偏好", text)

    def test_empty_task_is_usage(self):
        code, _, _ = run([unsupported_muse()], "who")
        self.assertEqual(code, 2)


class BriefTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "brief.md"
        self.ledger_path = Path(self.tmp.name) / "ledger.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def invoke(self, seats, *argv):
        from trinity_cli.state import Ledger

        out, err = io.StringIO(), io.StringIO()
        code = main(
            list(argv),
            seats=seats,
            out=out,
            err=err,
            stdin=io.StringIO(""),
            brief_path=self.path,
            ledger=Ledger(self.ledger_path),
        )
        return code, out.getvalue(), err.getvalue()

    def seats(self, world):
        world.supports_instructions = True
        world.instruction_text = "舊指令"
        return [
            DotSeat(FakeRunner(DotWorld()), binary="chatgpt-dot-cli", hostnames=set()),
            GrokSeat(FakeRunner(world), binary="/fake/bin/gbot", only_bots=[]),
            unsupported_muse(),
        ]

    def test_push_never_sends_to_dot_or_muse_and_requires_confirmation(self):
        world = GrokWorld(supports_instructions=True)
        world.instruction_text = "舊指令"
        dot = DotSeat(FakeRunner(DotWorld()), binary="chatgpt-dot-cli", hostnames=set())
        grok = GrokSeat(FakeRunner(world), binary="/fake/bin/gbot", only_bots=[])
        self.path.write_text("新的共同說明\n", encoding="utf-8")
        code, text, _ = self.invoke([dot, grok, unsupported_muse()], "brief", "push")
        self.assertEqual(code, 2)
        self.assertEqual(world.updates, [])
        self.assertNotIn("send", dot.runner.commands())
        self.assertNotIn("send", grok.runner.commands())
        self.assertIn("沒有送出", text)
        self.assertIn("沒有確認", text)
        self.assertIn("新的共同說明", text)

    def test_yes_updates_grok_only(self):
        world = GrokWorld(supports_instructions=True)
        world.instruction_text = "舊指令"
        dot = DotSeat(FakeRunner(DotWorld()), binary="chatgpt-dot-cli", hostnames=set())
        grok = GrokSeat(FakeRunner(world), binary="/fake/bin/gbot", only_bots=[])
        self.path.write_text("新的共同說明\n第二行", encoding="utf-8")
        code, text, _ = self.invoke([dot, grok, unsupported_muse()], "brief", "push", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual(len(world.updates), 1)
        self.assertIn("新的共同說明", world.updates[0]["text"])
        self.assertNotIn("send", dot.runner.commands())
        self.assertNotIn("send", grok.runner.commands())
        self.assertIn("已寫入", text)
        self.assertIn("沒有傳訊息", text)
        self.assertIn("沒有送出", text)

    def test_push_without_an_instruction_api_only_prints_a_draft(self):
        dot = DotSeat(FakeRunner(DotWorld()), binary="chatgpt-dot-cli", hostnames=set())
        grok = GrokSeat(FakeRunner(GrokWorld()), binary="/fake/bin/gbot", only_bots=[])
        self.path.write_text("草稿內容", encoding="utf-8")
        code, text, _ = self.invoke([dot, grok, unsupported_muse()], "brief", "push", "--yes")
        self.assertEqual(code, 0)
        self.assertNotIn("send", dot.runner.commands())
        self.assertNotIn("update", grok.runner.commands())
        self.assertIn("草稿內容", text)
        self.assertGreaterEqual(text.count("沒有送出"), 3)

    def test_diff_shows_a_difference_and_unsupported_seats(self):
        world = GrokWorld(supports_instructions=True)
        world.instruction_text = "舊指令"
        self.path.write_text("新的共同說明", encoding="utf-8")
        code, text, _ = self.invoke(self.seats(world), "brief", "diff")
        self.assertEqual(code, 0)
        self.assertIn("舊指令", text)
        self.assertIn("新的共同說明", text)
        self.assertIn("沒有指令 API", text)
        self.assertNotIn("send", world and [])

    def test_missing_diff_exits_zero_and_init_writes_once(self):
        code, text, _ = self.invoke([unsupported_muse()], "brief", "diff")
        self.assertEqual(code, 0)
        self.assertIn("還沒有 brief", text)
        self.assertIn("brief init", text)
        code, text, _ = self.invoke([unsupported_muse()], "brief", "init")
        self.assertEqual(code, 0)
        self.assertTrue(self.path.is_file())
        first = self.path.read_text(encoding="utf-8")
        self.assertIn("brief", first)
        code, text, _ = self.invoke([unsupported_muse()], "brief", "init")
        self.assertEqual(code, 0)
        self.assertIn("沒有覆寫", text)
        self.assertEqual(self.path.read_text(encoding="utf-8"), first)

    def test_show_and_missing_file(self):
        code, text, _ = self.invoke([unsupported_muse()], "brief", "show")
        self.assertEqual(code, 0)
        self.assertIn("還沒有 brief", text)
        self.path.write_text("只有這份", encoding="utf-8")
        code, text, _ = self.invoke([unsupported_muse()], "brief", "show")
        self.assertIn("只有這份", text)


class LogTests(unittest.TestCase):
    def test_filters_by_seat_status_and_since(self):
        from trinity_cli.state import Ledger

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ledger = Ledger(Path(tmp.name) / "ledger.jsonl")
        ledger.append({"event": "result", "seat": "dot", "target": "Your dot", "reply": "replied", "readback": "confirmed", "at": "2026-10-01T01:00:00+00:00"})
        ledger.append({"event": "result", "seat": "grok", "target": "Grok Bot/研究員", "reply": "timed_out", "readback": "not_seen", "at": "2026-10-01T02:00:00+00:00", "reply_key": "msg_secretkey0001"})
        ledger.append({"event": "not_sent", "seat": "dot", "target": "Your dot", "error": "token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.sig", "at": "2026-10-01T00:00:00+00:00"})
        out = io.StringIO()
        code = main(["log", "--seat", "dot", "--status", "replied"], seats=[unsupported_muse()], out=out, err=io.StringIO(), ledger=ledger)
        text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("replied", text)
        self.assertNotIn("timed_out", text)
        self.assertNotIn("msg_secretkey0001", text)
        out = io.StringIO()
        code = main(["log", "--seat", "dot", "--since", "100w"], seats=[unsupported_muse()], out=out, err=io.StringIO(), ledger=ledger)
        self.assertEqual(code, 0)
        self.assertIn("replied", out.getvalue())
        out = io.StringIO()
        main(["log", "--seat", "dot", "--status", "not_sent"], seats=[unsupported_muse()], out=out, err=io.StringIO(), ledger=ledger)
        self.assertNotIn("eyJ", out.getvalue())

    def test_json_omits_reply_keys(self):
        from trinity_cli.state import Ledger

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ledger = Ledger(Path(tmp.name) / "ledger.jsonl")
        ledger.append({"event": "wait", "seat": "dot", "target": "Your dot", "status": "seen", "reply_key": "msg_secretkey0001", "at": "2026-10-01T03:00:00+00:00"})
        out = io.StringIO()
        code = main(["log", "--json"], seats=[unsupported_muse()], out=out, err=io.StringIO(), ledger=ledger)
        data = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertNotIn("reply_key", data["records"][0])
        self.assertNotIn("msg_secretkey0001", out.getvalue())


if __name__ == "__main__":
    unittest.main()
