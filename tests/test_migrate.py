import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.fakes import Clock, FakeRunner, MuseWorld, ok
from trinity_cli.cli import main
from trinity_cli.migrate import PlanError, load_plan, run_migration
from trinity_cli.seats.muse import MuseSeat
from trinity_cli.state import Ledger


class ReplyingMuse(MuseWorld):
    """Muse that answers each message from a table keyed by a word in the text."""

    def __init__(self, answers: dict[str, str], **kw):
        super().__init__(**kw)
        self.answers = answers
        self.silent = False
        self.on_send = None

    def __call__(self, args, stdin):
        items = [a for a in args if a not in ("--autostart",)]
        if items and items[0] == "send":
            text = items[-1]
            self.reply = "" if self.silent else next((v for k, v in self.answers.items() if k in text), "ok")
            if self.on_send:
                self.on_send()
        return super().__call__(args, stdin)

    def sends(self) -> int:
        return sum(1 for c in self.calls if c and c[0] == "send")


class SideChatMuse(ReplyingMuse):
    """The api backend's chats: create/switch/list, plus send/messages scoped by --session."""

    def __init__(self, answers):
        super().__init__(answers)
        self.side: dict[str, dict] = {}
        self.switched = "main"
        self.deleted: list[str] = []
        self.counter = 0
        self.files: dict[str, str] = {}
        self.interject = False

    def __call__(self, args, stdin):
        items = [a for a in args if a != "--autostart"]
        backend = items[items.index("--backend") + 1] if "--backend" in items else None
        rest = [a for i, a in enumerate(items) if a != "--backend" and (i == 0 or items[i - 1] != "--backend")]
        command = rest[0]
        if backend == "api" and command == "chats":
            self.calls.append(rest)
            if "--create" in rest:
                self.counter += 1
                sid = f"s{self.counter}"
                self.side[sid] = {"title": rest[rest.index("--title") + 1], "messages": []}
                self.switched = sid
            if "--switch" in rest:
                self.switched = rest[rest.index("--switch") + 1]
            if "--delete" in rest:
                self.deleted.append(rest[rest.index("--delete") + 1])
                self.side.pop(rest[rest.index("--delete") + 1], None)
            chats = [{"title": None, "is_current": self.switched == "main", "kind": "main", "session_id": "main-id"}]
            chats += [{"title": c["title"], "is_current": self.switched == sid, "kind": "side", "session_id": sid} for sid, c in self.side.items()]
            return ok({"backend": "api", "state": "ok", "count": len(chats), "chats": chats, "error": None, "hint": None})
        if backend == "api" and "--session" in rest:
            sid = rest[rest.index("--session") + 1]
            chat = self.side[sid]["messages"]
            self.calls.append(rest)
            if command == "send":
                text = rest[-1]
                chat.append({"role": "user", "text": text, "presentation": False})
                if self.interject:
                    chat.append({"role": "assistant", "text": "Security alert: a withdrawal happened.", "presentation": False})
                # A fresh chat cannot see what was sent elsewhere: answers come from "files" only.
                known = self.files if "check" in self.side[sid]["title"] else self.answers
                chat.append({"role": "assistant", "text": next((v for k, v in known.items() if k in text), "ok"), "presentation": False})
                return ok({"backend": "api", "state": "ok", "attempted": True, "sent": True, "text": text, "reply": None, "error": None, "hint": None})
            if command == "messages":
                return ok({"backend": "api", "state": "ok", "name": "Muse", "lines": [], "messages": list(chat), "error": None, "hint": None})
        return super().__call__(args, stdin)


def plan(**over):
    base = {
        "format": "trinity-migration-plan", "version": 1, "id": "plan-abc123", "seat": "muse", "title": "Grok Bot: Deploy QA",
        "steps": [
            {"id": "intro", "text": "Moving Deploy QA to you. Reply saved intro.", "expectReply": ["saved"]},
            {"id": "memory-1", "text": "Save: watchlist resume-skills, telltale.", "expectReply": ["saved"]},
        ],
        "checks": [{"id": "memory", "kind": "memory", "contains": ["resume-skills", "telltale"]}],
        "questions": [{"area": "role", "text": "Who are you now?", "expect": ["Deploy QA"]}],
    }
    base.update(over)
    return base


class MigrateTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.ledger = Ledger(self.dir / "ledger.jsonl")
        self.clock = Clock()

    def tearDown(self):
        self.tmp.cleanup()

    def seat(self, world):
        return MuseSeat(FakeRunner(world), binary="muse-web-cli", clock=self.clock, sleep=self.clock.sleep)

    def write(self, value) -> Path:
        path = self.dir / "plan.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def run_plan(self, world, value, **kw):
        return run_migration(self.seat(world), load_plan(self.write(value)), ledger=self.ledger, timeout=30, poll=10,
                             path=self.dir / "state.json", **kw)

    def test_an_attached_file_goes_to_the_seat_and_its_bytes_are_bound_to_the_reply(self):
        bundle = self.dir / "bundle.zip"
        bundle.write_bytes(b"PK one")
        value = plan(steps=[{"id": "bundle", "text": "Unzip the attached bundle. Reply saved bundle.", "expectReply": ["saved"], "attach": [str(bundle)]}],
                     checks=[], questions=[])
        world = ReplyingMuse({"Unzip": "saved bundle"})
        result = self.run_plan(world, value)
        self.assertTrue(result["ok"], result)
        sent = next(c for c in world.calls if c and c[0] == "send")
        self.assertEqual(sent[sent.index("--attach") + 1], str(bundle))
        # Same text, other bytes: the old reply does not count for the new file.
        bundle.write_bytes(b"PK two")
        with self.assertRaises(PlanError):
            self.run_plan(world, value)
        for bad in ([], ["relative.zip"], [str(self.dir / "missing.zip")]):
            with self.assertRaises(PlanError):
                load_plan(self.write(plan(steps=[{"id": "b", "text": "x", "attach": bad}])))

    def test_sends_are_spaced_and_a_rate_limit_stops_the_run(self):
        world = ReplyingMuse({"Moving": "saved intro", "Save:": "saved memory-1", "Who are you": "Deploy QA"})
        world.memory_text = "resume-skills telltale"
        sends = []
        world.on_send = lambda: sends.append(self.clock.t)
        result = self.run_plan(world, plan(), min_interval=20)
        self.assertTrue(result["ok"], result)
        gaps = [b - a for a, b in zip(sends, sends[1:])]
        self.assertTrue(gaps and all(g >= 20 for g in gaps), gaps)
        from trinity_cli.migrate import _stop_note
        self.assertIn("太頻繁", _stop_note("memory-1", "send failed: 429 Too Many Requests"))

    def test_plan_validation_refuses_unknown_fields_seats_and_duplicates(self):
        for bad in (plan(extra=1), plan(seat="grok"), plan(steps=[{"id": "a", "text": "x"}, {"id": "a", "text": "y"}]),
                    plan(steps=[{"id": "a", "text": ""}]), plan(checks=[{"kind": "files", "contains": ["x"]}]), plan(format="other")):
            with self.assertRaises(PlanError):
                load_plan(self.write(bad))

    def test_full_run_delivers_reads_back_and_accepts(self):
        world = ReplyingMuse({"Moving": "saved intro", "Save:": "saved memory-1", "Who are you": "I am Deploy QA, migrated."})
        world.memory_text = "Grok watchlist: resume-skills, telltale"
        result = self.run_plan(world, plan())
        self.assertTrue(result["ok"], result)
        self.assertEqual([s["state"] for s in result["steps"]], ["replied", "replied"])
        self.assertEqual(result["checks"][0]["hits"], ["resume-skills", "telltale"])
        self.assertTrue(result["questions"][0]["ok"])
        self.assertEqual(world.sends(), 3)
        events = [r["event"] for r in self.ledger.records()]
        self.assertEqual(events.count("sending"), 3)
        state = json.loads((self.dir / "state.json").read_text())
        self.assertEqual(state["steps"]["intro"]["state"], "replied")

    def test_missing_memory_or_wrong_answer_is_not_ok(self):
        world = ReplyingMuse({"Moving": "saved", "Save:": "saved", "Who are you": "I am Muse."})
        world.memory_text = "nothing yet"
        result = self.run_plan(world, plan())
        self.assertFalse(result["ok"])
        self.assertFalse(result["checks"][0]["ok"])
        self.assertFalse(result["questions"][0]["ok"])

    def test_timeout_stops_and_a_rerun_reads_back_instead_of_resending(self):
        world = ReplyingMuse({"Moving": "saved intro", "Save:": "saved memory-1", "Who are you": "Deploy QA"})
        world.memory_text = "resume-skills telltale"
        world.silent = True
        first = self.run_plan(world, plan())
        self.assertFalse(first["ok"])
        self.assertEqual(first["steps"][0]["state"], "timed_out")
        self.assertEqual(world.sends(), 1)
        # The reply arrives later, after the run gave up.
        world.messages.append({"role": "assistant", "text": "saved intro", "presentation": False})
        world.silent = False
        second = self.run_plan(world, plan())
        self.assertTrue(second["ok"], second)
        self.assertEqual(second["steps"][0]["note"], "confirmed by read-back")
        intro_sends = sum(1 for c in world.calls if c and c[0] == "send" and "Moving" in c[-1])
        self.assertEqual(intro_sends, 1)

    def test_unknown_delivery_is_never_resent_without_the_flag(self):
        world = ReplyingMuse({"Moving": "saved", "Save:": "saved"})
        world.timeout_send = True
        first = self.run_plan(world, plan(checks=[], questions=[]))
        self.assertFalse(first["ok"])
        world.timeout_send = False
        second = self.run_plan(world, plan(checks=[], questions=[]))
        self.assertEqual(second["steps"][0]["state"], "unknown")
        self.assertEqual(world.sends(), 1)
        third = self.run_plan(world, plan(checks=[], questions=[]), resend_unknown=True)
        self.assertTrue(third["ok"], third)
        self.assertEqual(world.sends(), 3)

    def test_muse_plan_with_chat_runs_in_its_own_side_chat_and_leaves_main_current(self):
        world = SideChatMuse({"Moving": "saved intro", "Save:": "saved memory-1", "Who are you": "Deploy QA here"})
        world.memory_text = "resume-skills telltale"
        result = self.run_plan(world, plan(chat={"title": "Grok Bot · Deploy QA"}))
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["chat"], "chat:s1")
        self.assertEqual(world.switched, "main")
        self.assertEqual(len(world.side["s1"]["messages"]), 6)
        self.assertFalse(any(m["role"] == "user" for m in world.messages))
        # A second run reuses the same chat instead of creating another.
        again = self.run_plan(world, plan(chat={"title": "Grok Bot · Deploy QA"}))
        self.assertTrue(again["ok"])
        self.assertEqual(list(world.side), ["s1"])

    def test_questions_run_in_a_fresh_check_chat_that_is_deleted_afterwards(self):
        world = SideChatMuse({"Moving": "saved intro", "Save:": "saved memory-1", "Who are you": "Deploy QA (from chat context)"})
        world.files = {"Who are you": "I am Muse."}  # nothing durable was migrated
        world.memory_text = "unrelated"
        value = plan(chat={"title": "Grok Bot · Deploy QA"}, checkChat={"title": "Grok Bot · Deploy QA · check"},
                     checks=[{"id": "memory", "kind": "memory", "contains": ["Deploy QA"], "informational": True}])
        result = self.run_plan(world, value)
        self.assertFalse(result["ok"], "an answer only the migration chat could give must not pass")
        self.assertTrue(result["questions"][0]["fresh_chat"])
        self.assertIsNone(result["checks"][0]["ok"])
        self.assertEqual(world.deleted, ["s2"])
        self.assertEqual(list(world.side), ["s1"])
        self.assertEqual(world.switched, "main")
        world.files = {"Who are you": "Deploy QA, files in ~/grok-bot/Deploy-QA"}
        again = self.run_plan(world, value)
        self.assertTrue(again["ok"], again)

    def test_an_unrelated_agent_message_is_not_taken_as_the_reply(self):
        world = SideChatMuse({"Moving": "saved intro", "Save:": "saved memory-1"})
        world.files = {"Who are you": "Q1: Deploy QA"}
        world.interject = True
        value = plan(chat={"title": "Grok Bot · Deploy QA"}, checkChat={"title": "Grok Bot · Deploy QA · check"}, checks=[],
                     questions=[{"area": "role", "text": "Who are you now? Start your reply with Q1:", "expect": ["Deploy QA"], "marker": "Q1:"}])
        result = self.run_plan(world, value)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["steps"][0]["reply"], "saved intro")
        self.assertIn("Q1: Deploy QA", result["questions"][0]["answer"])

    def test_redo_resends_only_the_named_steps(self):
        world = ReplyingMuse({"Moving": "saved intro", "Save:": "saved memory-1", "Who are you": "Deploy QA"})
        world.memory_text = "resume-skills telltale"
        self.assertTrue(self.run_plan(world, plan())["ok"])
        before = world.sends()
        again = self.run_plan(world, plan(), redo=["memory-1"], questions=False)
        self.assertTrue(again["ok"], again)
        self.assertEqual(world.sends() - before, 1)
        with self.assertRaises(PlanError):
            self.run_plan(world, plan(), redo=["nope"])

    def test_keyword_matching_ignores_case_spaces_and_hyphens(self):
        from trinity_cli.migrate import _hits
        self.assertEqual(_hits("will Squash Merge it", ["squash-merge", "!65"]), ["squash-merge"])

    def test_cli_refuses_to_send_without_yes_when_not_a_terminal(self):
        world = ReplyingMuse({})
        out = io.StringIO()
        code = main(["--json", "migrate", "muse", str(self.write(plan()))], seats=[self.seat(world)], out=out,
                    err=io.StringIO(), ledger=self.ledger, stdin=io.StringIO(""))
        self.assertEqual(code, 2)
        self.assertEqual(world.sends(), 0)
        self.assertFalse(json.loads(out.getvalue())["ok"])

    def test_an_unreadable_or_foreign_state_file_stops_instead_of_starting_over(self):
        world = ReplyingMuse({"Moving": "saved intro", "Save:": "saved memory-1"})
        state = self.dir / "state.json"
        for bad in ("{not json", "[]", json.dumps({"plan_id": "other", "seat": "muse", "steps": {}}),
                    json.dumps({"plan_id": "plan-abc123", "seat": "muse", "steps": []})):
            state.write_text(bad, encoding="utf-8")
            with self.assertRaises(PlanError) as caught:
                self.run_plan(world, plan(checks=[], questions=[]))
            self.assertIn(str(state), str(caught.exception))
        self.assertEqual(world.sends(), 0)
        self.assertEqual(state.read_text(encoding="utf-8"), bad)

    def test_a_second_run_of_the_same_plan_fails_fast_while_the_first_is_running(self):
        world = ReplyingMuse({"Moving": "saved intro", "Save:": "saved memory-1"})
        value = plan(checks=[], questions=[])
        errors = []

        def second_run():
            world.on_send = None
            try:
                self.run_plan(world, value)
            except PlanError as exc:
                errors.append(str(exc))

        world.on_send = second_run
        (self.dir / "state.tmp").mkdir()  # a fixed temp name another run could share must not matter
        result = self.run_plan(world, value)
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(errors), 1)
        self.assertIn("state.json.lock", errors[0])
        self.assertEqual(world.sends(), 2)
        self.assertFalse([p.name for p in self.dir.iterdir() if p.name.startswith(".")])

    def test_a_step_changed_after_it_was_sent_needs_redo(self):
        world = ReplyingMuse({"Moving": "saved intro", "Save:": "saved memory-1"})
        self.assertTrue(self.run_plan(world, plan(checks=[], questions=[]))["ok"])
        changed = plan(checks=[], questions=[])
        changed["steps"][1]["text"] = "Save: watchlist resume-skills, telltale, and one more."
        with self.assertRaises(PlanError) as caught:
            self.run_plan(world, changed)
        self.assertIn("--redo memory-1", str(caught.exception))
        self.assertEqual(world.sends(), 2)
        again = self.run_plan(world, changed, redo=["memory-1"])
        self.assertTrue(again["ok"], again)
        self.assertEqual(world.sends(), 3)

    def test_a_reply_without_the_expected_words_stays_failed_on_resume(self):
        world = ReplyingMuse({"Moving": "noted", "Save:": "noted too"})
        value = plan(checks=[], questions=[])
        first = self.run_plan(world, value)
        self.assertEqual([s["ok"] for s in first["steps"]], [False, False])
        world.answers = {}
        second = self.run_plan(world, value)
        self.assertEqual([s["ok"] for s in second["steps"]], [False, False], "a resume must not turn a wrong reply into a pass")
        # Only a new matching reply to that step passes it; it is not intro's reply, since memory-1 came between.
        world.messages.append({"role": "assistant", "text": "saved memory-1", "presentation": False})
        third = self.run_plan(world, value)
        self.assertEqual([s["ok"] for s in third["steps"]], [False, True])
        self.assertEqual(world.sends(), 2)

    def test_a_reply_found_by_read_back_is_checked_against_expect_reply(self):
        world = ReplyingMuse({"Moving": "saved intro", "Save:": "saved memory-1"})
        world.silent = True
        self.run_plan(world, plan(checks=[], questions=[]))
        world.messages.append({"role": "assistant", "text": "noted", "presentation": False})
        world.silent = False
        second = self.run_plan(world, plan(checks=[], questions=[]))
        self.assertFalse(second["steps"][0]["ok"], second)
        self.assertFalse(second["ok"])

    def test_read_back_finds_a_reply_older_than_the_first_read_tail(self):
        world = ReplyingMuse({"Moving": "saved intro", "Save:": "saved memory-1"})
        world.silent = True
        self.run_plan(world, plan(checks=[], questions=[]))
        world.messages.append({"role": "assistant", "text": "saved intro", "presentation": False})
        world.messages += [{"role": "assistant", "text": f"Daily brief {i}", "presentation": False} for i in range(12)]
        world.silent = False
        second = self.run_plan(world, plan(checks=[], questions=[]))
        self.assertTrue(second["ok"], second)
        self.assertEqual(second["steps"][0]["note"], "confirmed by read-back")
        self.assertEqual(sum(1 for c in world.calls if c and c[0] == "send" and "Moving" in c[-1]), 1)

    def test_a_failed_read_back_fails_the_check_unless_informational(self):
        world = ReplyingMuse({"Moving": "saved intro", "Save:": "saved memory-1"})
        world.force["memory"] = "browser_down"
        result = self.run_plan(world, plan(questions=[]))
        self.assertFalse(result["ok"])
        self.assertIs(result["checks"][0]["ok"], False)
        self.assertTrue(result["checks"][0]["note"])
        info = self.run_plan(world, plan(questions=[], checks=[{"id": "memory", "kind": "memory", "contains": ["x"], "informational": True}]))
        self.assertIsNone(info["checks"][0]["ok"])
        self.assertTrue(info["ok"], info)

    def test_plan_validation_refuses_bad_min_and_marker_before_sending(self):
        check = lambda **kw: plan(checks=[{"id": "memory", "kind": "memory", "contains": ["a", "b"], **kw}])
        question = lambda **kw: plan(questions=[{"area": "role", "text": "Who?", "expect": ["Deploy QA"], **kw}])
        for bad in (check(min=-1), check(min=0), check(min=3), check(min=True), check(min="1"),
                    question(min=0), question(min=2), question(marker=""), question(marker="Q1"),
                    question(marker="Q1: "), question(marker="A1:"), question(marker=1)):
            with self.assertRaises(PlanError):
                load_plan(self.write(bad))
        load_plan(self.write(check(min=2)))
        load_plan(self.write(question(min=1, marker="Q12:")))

    def test_a_marker_matches_only_at_the_start_of_the_reply(self):
        world = SideChatMuse({"Moving": "saved intro", "Save:": "saved memory-1"})
        world.files = {"Who are you": "Q10: Deploy QA"}
        value = plan(chat={"title": "Grok Bot · Deploy QA"}, checkChat={"title": "Grok Bot · Deploy QA · check"}, checks=[],
                     questions=[{"area": "role", "text": "Who are you now? Start your reply with Q1:", "expect": ["Deploy QA"], "marker": "Q1:"}])
        result = self.run_plan(world, value)
        self.assertFalse(result["questions"][0]["ok"], "the answer to Q10 is not the answer to Q1")
        self.assertFalse(result["ok"])
        from trinity_cli.migrate import _has_marker
        for text in ("Q1: yes", "  **Q1:** yes", "> Q1: yes", "## `Q1:` yes", "_Q1:_ yes"):
            self.assertTrue(_has_marker(text, "Q1:"), text)
        for text in ("Q10: yes", "Answer Q1: yes", "q1: yes", "Q1 : yes"):
            self.assertFalse(_has_marker(text, "Q1:"), text)

    def test_the_check_chat_is_new_every_run_and_only_that_chat_is_deleted(self):
        from datetime import datetime, timezone
        world = SideChatMuse({"Moving": "saved intro", "Save:": "saved memory-1"})
        world.files = {"Who are you": "Deploy QA"}
        old_title = "Grok Bot · Deploy QA · check · 0101-000000"
        world.side["old"] = {"title": old_title, "messages": []}
        value = plan(chat={"title": "Grok Bot · Deploy QA"}, checkChat={"title": "Grok Bot · Deploy QA · check"}, checks=[])
        fixed = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertTrue(self.run_plan(world, value, now=lambda: fixed)["ok"])
        self.assertTrue(self.run_plan(world, value, now=lambda: fixed)["ok"])
        self.assertIn("old", world.side)
        self.assertNotIn("old", world.deleted)
        titles = [c[c.index("--title") + 1] for c in world.calls if "--create" in c][1:]
        self.assertEqual(len(titles), 2)
        self.assertNotEqual(titles[0], titles[1])
        self.assertTrue(all("plan-abc123" in t for t in titles), titles)
        self.assertEqual(len(world.deleted), 2)
        self.assertEqual(sorted(world.side), ["old", "s1"])
        seat = self.seat(world)
        self.assertEqual(seat.open_chat(old_title).value, ("chat:old", False))
        target, created = seat.open_chat(old_title, create_only=True).value
        self.assertTrue(created)
        self.assertNotEqual(target, "chat:old")

    def test_check_only_sends_no_step_and_reports_undelivered_steps(self):
        world = ReplyingMuse({"Moving": "saved intro", "Save:": "saved memory-1", "Who are you": "Deploy QA"})
        world.memory_text = "resume-skills telltale"
        world.silent = True
        self.run_plan(world, plan())
        world.silent = False
        world.messages.append({"role": "assistant", "text": "saved intro", "presentation": False})  # arrives late
        step_sends = lambda: sum(1 for c in world.calls if c and c[0] == "send" and ("Moving" in c[-1] or "Save:" in c[-1]))
        result = self.run_plan(world, plan(), check_only=True)
        self.assertEqual(step_sends(), 1)
        self.assertEqual([s["state"] for s in result["steps"]], ["not delivered", "not delivered"])
        self.assertFalse(result["ok"])
        self.assertIsNone(result["stopped"])
        self.assertTrue(result["checks"][0]["ok"])
        self.assertTrue(result["questions"][0]["ok"])
        with self.assertRaises(PlanError):
            self.run_plan(world, plan(), check_only=True, redo=["intro"])
        # Once every step is delivered and acknowledged, a check-only run passes without sending.
        self.assertTrue(self.run_plan(world, plan())["ok"])
        self.assertEqual(step_sends(), 2)
        again = self.run_plan(world, plan(), check_only=True)
        self.assertTrue(again["ok"], again)
        self.assertEqual(step_sends(), 2)

    def test_cli_check_only_needs_no_yes_and_refuses_redo(self):
        world = ReplyingMuse({"Who are you": "Deploy QA"})
        path = str(self.write(plan(checks=[])))
        out = io.StringIO()
        home = mock.patch.dict(os.environ, {"TRINITY_HOME": str(self.dir / "home")})
        home.start()
        self.addCleanup(home.stop)
        code = main(["--json", "migrate", "muse", path, "--check-only"], seats=[self.seat(world)], out=out,
                    err=io.StringIO(), ledger=self.ledger, stdin=io.StringIO(""))
        self.assertEqual(code, 1)
        self.assertEqual([s["state"] for s in json.loads(out.getvalue())["steps"]], ["not delivered", "not delivered"])
        self.assertFalse(any(c and c[0] == "send" and "Moving" in c[-1] for c in world.calls))
        code = main(["--json", "migrate", "muse", path, "--check-only", "--redo", "intro"], seats=[self.seat(world)],
                    out=io.StringIO(), err=io.StringIO(), ledger=self.ledger, stdin=io.StringIO(""))
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()


class DotAttachTests(unittest.TestCase):
    def test_dot_send_passes_each_file_to_chatgpt_dot_cli(self):
        from tests.fakes import DotWorld
        from trinity_cli.seats.dot import DotSeat

        world = DotWorld()
        runner = FakeRunner(world)
        seat = DotSeat(runner, binary="chatgpt-dot-cli", hostnames=set(), clock=Clock(), sleep=lambda s: None)
        result = seat.send(None, "unzip it", "n0nce", attach=["/abs/a.zip", "/abs/b.md"])
        self.assertEqual(result.state, "ok", result)
        argv = next(c["argv"] for c in runner.calls if "send" in c["argv"])
        self.assertEqual([argv[i + 1] for i, a in enumerate(argv) if a == "--attach"], ["/abs/a.zip", "/abs/b.md"])
        self.assertLess(argv.index("--attach"), argv.index("--"))
