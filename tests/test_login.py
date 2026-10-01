"""Login commands. These tests never start muse, muse-web-cli, codex, or a browser."""

import io
import json
import unittest

from tests.fakes import FAKE_JWT, FakeRunner
from trinity_cli.cli import main
from trinity_cli.runner import LOGIN_TIMEOUT, Proc
from trinity_cli.seats.dot import DotSeat
from trinity_cli.seats.grok import GrokSeat
from trinity_cli.seats.muse import MuseSeat

SECRET = "token=sekret-value"


def _proc(code=0, out="", err="", timed_out=False):
    return Proc(code, out, err, timed_out)


def _runner(proc):
    return FakeRunner(lambda args, stdin: proc)


def _run(seats, *argv):
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), seats=seats, out=out, err=err, stdin=io.StringIO(""))
    return code, out.getvalue(), err.getvalue()


class MuseLoginTests(unittest.TestCase):
    def test_token_login_calls_credential_and_drops_child_output(self):
        payload = {
            "state": "ok",
            "wrote": True,
            "logged_in": True,
            "fields": {
                "base_url": True,
                "vm_id": True,
                "auth.type": True,
                "auth.token": True,
                "timeout_s": True,
                "notary_token": False,
            },
            "token": FAKE_JWT,
            "error": None,
            "hint": None,
        }
        runner = _runner(_proc(0, json.dumps(payload), SECRET))
        seat = MuseSeat(runner, binary="/fake/bin/muse-web-cli", token_binary="/fake/bin/muse")
        code, text, err = _run([seat], "login", "muse")
        self.assertEqual(code, 0, err)
        call = runner.calls[0]
        self.assertEqual(call["argv"], ["/fake/bin/muse-web-cli", "--json", "credential"])
        self.assertFalse(call.get("attach"))
        self.assertEqual(call["timeout"], LOGIN_TIMEOUT)
        self.assertNotIn("auth.json", " ".join(call["argv"]))
        self.assertNotIn("--autostart", call["argv"])
        self.assertIn("muse-credential", text)
        self.assertIn("沒有印出 token", text)
        self.assertIn("auth.token", text)
        self.assertNotIn(FAKE_JWT, text)
        self.assertNotIn("sekret-value", text)
        self.assertNotIn(FAKE_JWT, err)

    def test_api_key_goes_to_muse_auth_set_stdin_flag_only(self):
        runner = _runner(_proc(0, FAKE_JWT, SECRET))
        seat = MuseSeat(runner, binary="muse-web-cli", token_binary="/fake/bin/muse")
        code, text, _ = _run([seat], "--json", "login", "muse", "--api-key")
        self.assertEqual(code, 0)
        self.assertEqual(
            runner.calls[0]["argv"],
            ["/fake/bin/muse", "auth", "set", "--provider", "meta", "--api-key-stdin"],
        )
        data = json.loads(text)
        self.assertTrue(data["ok"])
        self.assertIn("沒有保存金鑰", data["message"])
        self.assertNotIn(FAKE_JWT, text)
        self.assertNotIn("sekret-value", text)

    def test_web_login_uses_muse_web_cli_without_autostart_and_hides_the_port(self):
        payload = {
            "state": "ok",
            "logged_in": True,
            "port": 59999,
            "pid": 424242,
            "hint": None,
            "ignored": FAKE_JWT,
        }
        runner = _runner(_proc(0, json.dumps(payload), SECRET))
        seat = MuseSeat(runner, binary="/fake/bin/muse-web-cli", token_binary="/fake/bin/muse")
        code, text, _ = _run([seat], "login", "muse", "--web")
        self.assertEqual(code, 0)
        self.assertEqual(runner.calls[0]["argv"], ["/fake/bin/muse-web-cli", "--json", "login"])
        self.assertNotIn("--autostart", runner.calls[0]["argv"])
        self.assertNotIn("attach", runner.calls[0])
        self.assertIn("Muse 網頁已登入", text)
        self.assertNotIn("59999", text)
        self.assertNotIn("424242", text)
        self.assertNotIn(FAKE_JWT, text)
        self.assertNotIn("sekret-value", text)

    def test_web_login_not_finished_does_not_count_as_success(self):
        payload = {"state": "ok", "logged_in": False, "port": 59999, "hint": "muse-web-cli login"}
        runner = _runner(_proc(0, json.dumps(payload)))
        seat = MuseSeat(runner, binary="/fake/bin/muse-web-cli", token_binary="/fake/bin/muse")
        code, text, _ = _run([seat], "login", "muse", "--web")
        self.assertEqual(code, 1)
        self.assertIn("Chrome 視窗", text)
        self.assertNotIn("59999", text)

    def test_missing_muse_web_cli_does_not_spawn_for_credential(self):
        runner = _runner(_proc())
        seat = MuseSeat(runner, binary="", token_binary="/fake/bin/muse")
        code, text, _ = _run([seat], "login", "muse")
        self.assertEqual(code, 1)
        self.assertIn("找不到 muse-web-cli", text)
        self.assertEqual(runner.calls, [])

    def test_failed_credential_keeps_the_child_output_out(self):
        runner = _runner(_proc(1, FAKE_JWT, SECRET))
        seat = MuseSeat(runner, binary="/fake/bin/muse-web-cli", token_binary="/fake/bin/muse")
        code, text, _ = _run([seat], "login", "muse")
        self.assertEqual(code, 1)
        self.assertIn("沒有寫入", text)
        self.assertNotIn(FAKE_JWT, text)
        self.assertNotIn("sekret-value", text)

    def test_flags_cannot_be_combined_or_used_on_another_seat(self):
        runner = _runner(_proc())
        muse = MuseSeat(runner, binary="muse-web-cli", token_binary="/fake/bin/muse")
        code, _, err = _run([muse], "login", "muse", "--api-key", "--web")
        self.assertEqual(code, 2)
        self.assertIn("不能同時", err)
        self.assertEqual(runner.calls, [])
        dot = DotSeat(runner, binary="chatgpt-dot-cli", hostnames=set(), codex="/fake/bin/codex")
        code, _, err = _run([dot], "login", "dot", "--web")
        self.assertEqual(code, 2)
        self.assertIn("只有 Muse", err)
        self.assertEqual(runner.calls, [])


class OtherSeatLoginTests(unittest.TestCase):
    def test_dot_runs_codex_login_and_never_passes_an_auth_path(self):
        runner = _runner(_proc(0, FAKE_JWT, SECRET))
        seat = DotSeat(runner, binary="chatgpt-dot-cli", hostnames=set(), codex="/fake/bin/codex")
        code, text, _ = _run([seat], "login", "dot")
        self.assertEqual(code, 0)
        argv = runner.calls[0]["argv"]
        self.assertEqual(argv, ["/fake/bin/codex", "login"])
        self.assertTrue(runner.calls[0]["attach"])
        self.assertFalse(any("auth" in part for part in argv))
        self.assertNotIn(FAKE_JWT, text)
        self.assertNotIn("sekret-value", text)

    def test_grok_does_not_touch_the_app_session(self):
        runner = _runner(_proc(0, FAKE_JWT, SECRET))
        seat = GrokSeat(runner, binary="/fake/bin/gbot", only_bots=[])
        code, text, _ = _run([seat], "login", "grok")
        self.assertEqual(code, 1)
        self.assertIn("Grok Bot app", text)
        self.assertIn("不讀", text)
        self.assertEqual(runner.calls, [])
        self.assertNotIn(FAKE_JWT, text)


if __name__ == "__main__":
    unittest.main()
