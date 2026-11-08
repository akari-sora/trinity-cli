import io
import json
import tempfile
import unittest
from pathlib import Path

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

    def __call__(self, args, stdin):
        items = [a for a in args if a not in ("--autostart",)]
        if items and items[0] == "send":
            text = items[-1]
            self.reply = "" if self.silent else next((v for k, v in self.answers.items() if k in text), "ok")
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
                known = self.files if self.side[sid]["title"].endswith(tuple("0123456789")) else self.answers
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


if __name__ == "__main__":
    unittest.main()
