import os
import tempfile
import unittest
from pathlib import Path

from tests.fakes import BOT_ID, DotWorld, FakeRunner, GrokWorld, dot_message
from trinity_cli.config import clean_account, configured_gbot_account
from trinity_cli.seats import DotSeat, GrokSeat, MuseSeat
from trinity_cli.util import WINDOW_CURSOR


class AccountTests(unittest.TestCase):
    def test_flag_and_env_when_gbot_documents_account(self):
        world = GrokWorld(supports_account=True)
        runner = FakeRunner(world)
        seat = GrokSeat(runner, binary="/fake/bin/gbot", only_bots=[], account="work")
        self.assertEqual(seat.status().state, "ok")
        bots = next(call for call in runner.calls if "bots" in call["argv"])
        self.assertEqual(bots["argv"][bots["argv"].index("--account") + 1], "work")
        self.assertEqual(bots["env"]["GBOT_ACCOUNT"], "work")
        help_call = next(call for call in runner.calls if call["argv"][1:] == ["--help"])
        self.assertNotIn("--account", help_call["argv"])

    def test_unknown_flag_is_not_passed(self):
        world = GrokWorld()
        runner = FakeRunner(world)
        seat = GrokSeat(runner, binary="/fake/bin/gbot", only_bots=[], account="work")
        self.assertEqual(seat.status().state, "ok")
        for call in runner.calls:
            self.assertNotIn("--account", call["argv"])
        bots = next(call for call in runner.calls if "bots" in call["argv"])
        self.assertEqual(bots["env"]["GBOT_ACCOUNT"], "work")

    def test_thread_after_keeps_extra_fields(self):
        world = GrokWorld(
            transcripts={BOT_ID: [self._entry("e1", "user", "q"), self._entry("e2", "assistant", "a")]},
            supports_after=True,
        )
        seat = GrokSeat(FakeRunner(world), binary="/fake/bin/gbot", only_bots=[])
        batch = seat.read({f"grok.{BOT_ID}": {"id": "e1"}}).value.batches[0]
        self.assertEqual([item.text for item in batch.items], ["a"])
        self.assertEqual(batch.new_cursor, {"id": "e2"})
        self.assertFalse(batch.gap)

    def test_window_cursor_is_not_sent_as_after(self):
        world = GrokWorld(transcripts={BOT_ID: [self._entry("e1", "assistant", "kept")]}, supports_after=True)
        runner = FakeRunner(world)
        seat = GrokSeat(runner, binary="/fake/bin/gbot", only_bots=[])
        batch = seat.read({"*": dict(WINDOW_CURSOR)}).value.batches[0]
        thread = next(call["argv"] for call in runner.calls if "thread" in call["argv"])
        self.assertNotIn("--after", thread)
        self.assertEqual([item.text for item in batch.items], ["kept"])

    def test_dot_ignores_unknown_json_fields(self):
        message = dot_message(1, "dot", "hi", "2026-10-01T01:00:00Z")
        message["future_field"] = {"entryCount": 1, "cursor": "later"}
        world = DotWorld(messages=[message])
        world.dot["brand_new"] = {"ok": True}
        result = DotSeat(FakeRunner(world), binary="chatgpt-dot-cli", hostnames=set()).read({})
        self.assertEqual(result.state, "ok")
        self.assertEqual(result.value.batches[0].items[-1].text, "hi")

    def test_config_account_and_token_rejection(self):
        self.assertIsNone(clean_account("eyJhbGciOiJIUzI1NiJ9.payload.signature"))
        self.assertIsNone(clean_account("sk-proj1234567890abcdef"))
        self.assertEqual(clean_account("work"), "work")
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "config.json").write_text('{"gbot_account": "desk"}', encoding="utf-8")
            old_account = os.environ.pop("TRINITY_GBOT_ACCOUNT", None)
            old_home = os.environ.get("TRINITY_HOME")
            os.environ["TRINITY_HOME"] = tmp
            try:
                self.assertEqual(configured_gbot_account(), "desk")
                os.environ["TRINITY_GBOT_ACCOUNT"] = "env-name"
                self.assertEqual(configured_gbot_account(), "env-name")
                os.environ["TRINITY_GBOT_ACCOUNT"] = "eyJhbGciOiJIUzI1NiJ9.payload.signature"
                self.assertIsNone(configured_gbot_account())
            finally:
                if old_account is None:
                    os.environ.pop("TRINITY_GBOT_ACCOUNT", None)
                else:
                    os.environ["TRINITY_GBOT_ACCOUNT"] = old_account
                if old_home is None:
                    os.environ.pop("TRINITY_HOME", None)
                else:
                    os.environ["TRINITY_HOME"] = old_home

    def test_new_capabilities_default_to_unsupported(self):
        muse = MuseSeat()
        self.assertFalse(muse.supports("schedules"))
        self.assertFalse(muse.supports("instructions"))
        self.assertEqual(muse.schedules().state, "unsupported")
        self.assertEqual(muse.instructions(update="do not send").state, "unsupported")
        dot = DotSeat(FakeRunner(DotWorld()), binary="chatgpt-dot-cli", hostnames=set())
        self.assertTrue(dot.supports("schedules"))
        self.assertFalse(dot.supports("instructions"))
        self.assertEqual(dot.instructions(update="nope").state, "unsupported")
        grok = GrokSeat(FakeRunner(GrokWorld()), binary="/fake/bin/gbot", only_bots=[])
        self.assertEqual(grok.schedules().state, "unsupported")
        self.assertIn("沒有排程", grok.schedules().error)
        self.assertEqual(grok.instructions(update="nope").state, "unsupported")
        missing = GrokSeat(FakeRunner(GrokWorld()), binary="", only_bots=[])
        self.assertEqual(missing.schedules().state, "failed")
        self.assertIn("找不到 gbot", missing.schedules().error)
        self.assertIn("沒有寫入", missing.instructions(update="nope").error)

    def test_entry_count_without_a_transcript_is_empty(self):
        from trinity_cli.seats.grok import transcript_entries

        self.assertEqual(transcript_entries({"cursor": "e9", "entryCount": 0, "gapReset": False, "extra": {"n": 1}}), [])

    @staticmethod
    def _entry(entry_id, role, text):
        return {"id": entry_id, "role": role, "text": text, "future": {"gapReset": False}}


class ScheduleAdapterTests(unittest.TestCase):
    def test_dot_automations_keep_unknown_fields(self):
        world = DotWorld()
        world.automations = [{"title": "晨間摘要", "schedule": {"expression": "0 8 * * *"}, "status": "ACTIVE", "extra": 1}]
        result = DotSeat(FakeRunner(world), binary="chatgpt-dot-cli", hostnames=set()).schedules()
        self.assertEqual(result.state, "ok")
        self.assertEqual(result.value[0].title, "晨間摘要")
        self.assertEqual(result.value[0].when, "0 8 * * *")
        self.assertEqual(result.value[0].status, "ACTIVE")

    def test_grok_routines_when_the_cli_has_them(self):
        world = GrokWorld(supports_schedules=True)
        world.schedule_items = [{"name": "晨間摘要", "cron": "0 8 * * *", "enabled": True}]
        result = GrokSeat(FakeRunner(world), binary="/fake/bin/gbot", only_bots=[]).schedules()
        self.assertEqual(result.state, "ok")
        self.assertEqual(result.value[0].title, "晨間摘要")
        self.assertEqual(result.value[0].when, "0 8 * * *")
        self.assertEqual(result.value[0].status, "enabled")


if __name__ == "__main__":
    unittest.main()
