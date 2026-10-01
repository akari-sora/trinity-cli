import io
import json
import unittest

from tests.fakes import (
    DotWorld,
    FakeRunner,
    FakeSeat,
    GrokWorld,
    dot_message,
    fail,
    grok_entry,
    ok,
    BOT_ID,
    unsupported_muse,
)
from trinity_cli.cli import main
from trinity_cli.model import Result, SeatStatus
from trinity_cli.seats import DotSeat, GrokSeat


def run(seats, *argv):
    out = io.StringIO()
    code = main(list(argv) or ["status"], seats=seats, out=out)
    return code, out.getvalue()


def dot_seat(world):
    return DotSeat(FakeRunner(world), binary="chatgpt-dot-cli", hostnames={"macbook-pro-5"})


def grok_seat(world):
    return GrokSeat(FakeRunner(world), binary="/fake/bin/gbot", only_bots=[])


class StatusCommandTests(unittest.TestCase):
    def test_unsupported_seat_does_not_fail_status(self):
        good = FakeSeat("a", "Alpha", status=Result.ok(SeatStatus("運作中")))
        code, text = run([good, unsupported_muse()], "status")
        self.assertEqual(code, 0)
        self.assertIn("Muse", text)
        self.assertIn("不支援", text)
        self.assertNotIn("✗", text)

    def test_unsupported_seat_in_json(self):
        good = FakeSeat("a", "Alpha", status=Result.ok(SeatStatus("運作中")))
        code, text = run([good, unsupported_muse()], "--json", "status")
        data = json.loads(text)
        self.assertEqual(code, 0)
        self.assertEqual([s["state"] for s in data["seats"]], ["ok", "unsupported"])

    def test_failing_seat_is_shown_as_failure_with_its_hint(self):
        bad = FakeSeat("b", "Beta", status=Result.failed("連不上", "去修它"))
        good = FakeSeat("a", "Alpha", status=Result.ok(SeatStatus("運作中")))
        code, text = run([good, bad, unsupported_muse()], "status")
        self.assertEqual(code, 0)
        line = next(l for l in text.splitlines() if l.startswith("Beta"))
        self.assertIn("✗ 失敗：連不上", line)
        self.assertIn("→ 去修它", line)
        self.assertIn("Alpha", text)

    def test_crashing_adapter_only_fails_its_own_seat(self):
        def boom():
            raise RuntimeError("adapter bug")

        good = FakeSeat("a", "Alpha", status=Result.ok(SeatStatus("運作中")))
        code, text = run([FakeSeat("c", "Crash", status=boom), good], "status")
        self.assertEqual(code, 0)
        self.assertIn("Crash  ✗ 失敗：Crash status 內部錯誤", text)
        self.assertIn("Alpha  ✓ 運作中", text)

    def test_waiting_items_are_printed_first(self):
        seat = FakeSeat("a", "Alpha", status=Result.ok(SeatStatus("運作中", waiting=["Alpha 在等你"])))
        code, text = run([unsupported_muse(), seat], "status")
        self.assertEqual(text.splitlines()[0], "等你處理：")
        self.assertIn("Alpha 在等你", text.splitlines()[1])


class DotStatusTests(unittest.TestCase):
    def test_reads_every_part_from_cli_json(self):
        world = DotWorld(messages=[dot_message(1, "you", "hi", "2026-10-01T01:00:00Z"),
                                   dot_message(2, "dot", "進度更新", "2026-10-01T02:00:00Z")])
        result = dot_seat(world).status()
        self.assertEqual(result.state, "ok")
        summary = result.value.summary
        for part in ("運作中", "這台 Mac 已連接", "電腦 1/2 已連接", "環境 connected", "額度已用 20%"):
            self.assertIn(part, summary)
        self.assertTrue(any("最後一句是 dot 說的" in w and "未讀" in w for w in result.value.waiting))

    def test_uses_only_fast_calls(self):
        world = DotWorld()
        seat = dot_seat(world)
        seat.status()
        commands = set(seat.runner.commands())
        self.assertNotIn("summary", commands)
        self.assertNotIn("activity", commands)

    def test_expired_login_says_codex_login(self):
        world = DotWorld()
        world.overrides["list"] = fail(3, "ChatGPT login expired (401). Open Codex or run `codex login`, then retry.")
        result = dot_seat(world).status()
        self.assertEqual(result.state, "failed")
        self.assertIn("401", result.error)
        self.assertIn("codex login", result.hint)

    def test_bad_auth_file_says_codex_login(self):
        world = DotWorld()
        world.overrides["list"] = fail(2, "cannot read auth file: No such file or directory")
        result = dot_seat(world).status()
        self.assertEqual(result.state, "failed")
        self.assertIn("codex login", result.hint)

    def test_one_broken_part_is_a_visible_problem(self):
        world = DotWorld()
        world.overrides["usage"] = fail(3, "network error: timed out")
        result = dot_seat(world).status()
        self.assertEqual(result.state, "ok")
        self.assertIn("額度 ✗", result.value.summary)
        self.assertTrue(result.value.problems)
        self.assertTrue(result.value.hint)

    def test_paused_dot_is_waiting_on_you(self):
        from tests.fakes import dot_record

        world = DotWorld(dot=dot_record(paused=True))
        result = dot_seat(world).status()
        self.assertIn("已暫停", result.value.summary)
        self.assertTrue(any("已暫停" in w for w in result.value.waiting))

    def test_missing_cli_is_a_failure(self):
        result = DotSeat(FakeRunner(DotWorld()), binary="").status()
        self.assertEqual(result.state, "failed")
        self.assertIn("chatgpt-dot-cli", result.error)


class GrokStatusTests(unittest.TestCase):
    def test_ambiguous_app_session_names_the_fix(self):
        world = GrokWorld()
        world.overrides["bots"] = fail(
            1, "Grok Bot gateway descriptor has multiple saved gateway entries and no active entry selection."
        )
        world.doctor = {"gatewayAuthPresent": True, "grokBotAppSession": {"present": True, "usable": False, "code": "AMBIGUOUS_ENTRIES"}}
        result = grok_seat(world).status()
        self.assertEqual(result.state, "failed")
        self.assertIn("多個 gateway 登入", result.error)
        self.assertIn("Grok Bot app", result.hint)
        self.assertIn("gbot doctor", result.hint)

    def test_missing_gbot_is_a_failure(self):
        result = GrokSeat(FakeRunner(GrokWorld()), binary="").status()
        self.assertEqual(result.state, "failed")
        self.assertIn("gbot", result.error)

    def test_shows_each_bot_last_message(self):
        world = GrokWorld(transcripts={BOT_ID: [grok_entry("e1", "user", "hi"),
                                                grok_entry("e2", "assistant", "done", "2026-10-01T02:00:00Z")]})
        result = grok_seat(world).status()
        self.assertEqual(result.state, "ok")
        self.assertIn("蝴蝶 最後訊息", result.value.summary)
        self.assertIn("（bot）", result.value.summary)
        self.assertTrue(any("蝴蝶 最後一句是 bot 說的" in w for w in result.value.waiting))

    def test_real_seats_side_by_side_never_print_ids(self):
        dot = dot_seat(DotWorld(messages=[dot_message(1, "dot", "ok", "2026-10-01T02:00:00Z")]))
        grok_world = GrokWorld()
        grok_world.overrides["bots"] = fail(1, "gateway error for agent 0b0e7a8c-1111-4222-8333-444455556666")
        code, text = run([dot, grok_seat(grok_world), unsupported_muse()], "status")
        self.assertEqual(code, 0)
        self.assertIn("Grok Bot  ✗ 失敗", text)
        self.assertNotIn("0b0e7a8c", text)


if __name__ == "__main__":
    unittest.main()
