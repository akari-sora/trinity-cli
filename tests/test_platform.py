"""Windows branches. These tests never start a real child process."""

import inspect
import subprocess
import unittest
from unittest import mock

from trinity_cli.cli import configure_stdio
from trinity_cli.runner import Runner, command_argv, find_tool
from trinity_cli.state import Ledger
from trinity_cli.seats.muse import credential_mode_fix


class _Proc:
    def __init__(self, args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.pid = 4242
        self.returncode = 0
        self.killed = False
        self.timeouts_left = 1 if kwargs.pop("_timeout", False) else 0

    def communicate(self, input=None, timeout=None):
        if self.timeouts_left:
            self.timeouts_left -= 1
            raise subprocess.TimeoutExpired(self.args, timeout or 1)
        return "ok", ""

    def wait(self, timeout=None):
        if self.timeouts_left:
            self.timeouts_left -= 1
            raise subprocess.TimeoutExpired(self.args, timeout or 1)
        return 0

    def kill(self):
        self.killed = True


class PlatformTests(unittest.TestCase):
    def test_windows_shim_is_resolved_by_which_and_not_a_shell(self):
        shim = r"C:\Users\me\AppData\Roaming\npm\gbot.cmd"
        with mock.patch("trinity_cli.runner.os.name", "nt"), mock.patch(
            "trinity_cli.runner.shutil.which", return_value=shim
        ) as which, mock.patch.dict("os.environ", {"COMSPEC": "cmd.exe"}), mock.patch(
            "trinity_cli.runner.npm_shim_target", return_value=None
        ):
            found = find_tool("gbot", "TRINITY_GBOT_UNSET")
            wrapped = command_argv([found, "--json", "bots", "list"])
        which.assert_called_once_with("gbot")
        self.assertEqual(found, shim)
        self.assertEqual(wrapped, f'"cmd.exe" /d /s /c ""{shim}" "--json" "bots" "list""')

    def test_npm_shim_runs_node_directly_so_cmd_never_sees_the_message(self):
        import tempfile
        from pathlib import Path

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        npm = Path(tmp.name, "John Smith", "npm")
        script = npm / "node_modules" / "grok-bot-cli" / "bin" / "gbot.mjs"
        script.parent.mkdir(parents=True)
        script.write_text("", encoding="utf-8")
        (npm / "node.exe").write_text("", encoding="utf-8")
        shim = npm / "gbot.cmd"
        shim.write_text(
            '@ECHO off\r\nIF EXIST "%dp0%\\node.exe" (\r\n  SET "_prog=%dp0%\\node.exe"\r\n)\r\n'
            'endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & "%_prog%"  '
            '"%dp0%\\node_modules\\grok-bot-cli\\bin\\gbot.mjs" %*\r\n',
            encoding="utf-8",
        )
        from trinity_cli.runner import npm_shim_target

        direct = npm_shim_target(str(shim))
        self.assertEqual(direct, [str(npm / "node.exe"), str(script)])
        message = 'line one\nline "two" 100%PATH% a&b'
        # Patching os.name makes pathlib build Windows paths, so hand command_argv the parsed shim.
        with mock.patch("trinity_cli.runner.os.name", "nt"), mock.patch("trinity_cli.runner.npm_shim_target", return_value=direct):
            argv = command_argv([str(shim), "bots", "update", "x", "--instructions", message])
        self.assertEqual(argv, [*direct, "bots", "update", "x", "--instructions", message])

    def test_other_batch_files_quote_every_argument_and_refuse_what_cmd_cannot_carry(self):
        from trinity_cli.runner import UnsafeCommand

        tool = r"C:\Users\John Smith\bin\tool.bat"
        with mock.patch("trinity_cli.runner.os.name", "nt"), mock.patch.dict(
            "os.environ", {"COMSPEC": r"C:\Windows\system32\cmd.exe"}
        ), mock.patch("trinity_cli.runner.npm_shim_target", return_value=None):
            line = command_argv([tool, "x&y", "a b", "C:\\dir\\"])
            self.assertEqual(line, r'"C:\Windows\system32\cmd.exe" /d /s /c ""C:\Users\John Smith\bin\tool.bat" "x&y" "a b" "C:\dir\\""')
            for bad in ('say "hi"', "100%PATH%", "two\nlines"):
                with self.assertRaises(UnsafeCommand):
                    command_argv([tool, bad])
            proc = Runner().run([tool, "two\nlines"])
        self.assertEqual(proc.code, 2)
        self.assertIn(".cmd", proc.err)

    def test_posix_argv_is_unchanged(self):
        with mock.patch("trinity_cli.runner.os.name", "posix"):
            self.assertEqual(command_argv(["gbot", "--json"]), ["gbot", "--json"])

    def test_run_decodes_utf8_and_never_uses_a_shell(self):
        seen = {}

        def popen(args, **kwargs):
            seen["args"] = args
            seen["kwargs"] = kwargs
            return _Proc(args, **kwargs)

        with mock.patch("trinity_cli.runner.os.name", "posix"), mock.patch(
            "trinity_cli.runner.subprocess.Popen", popen
        ):
            result = Runner().run(["chatgpt-dot-cli", "--json", "list"], stdin="你好", timeout=3)
        self.assertEqual(result.code, 0)
        self.assertEqual(result.out, "ok")
        self.assertFalse(seen["kwargs"]["shell"])
        self.assertEqual(seen["kwargs"]["encoding"], "utf-8")
        self.assertEqual(seen["kwargs"]["errors"], "replace")
        self.assertNotIn("preexec_fn", seen["kwargs"])
        self.assertNotIn("start_new_session", seen["kwargs"])
        self.assertEqual(seen["args"], ["chatgpt-dot-cli", "--json", "list"])

    def test_windows_timeout_uses_taskkill_tree_not_a_posix_signal(self):
        calls = []

        def popen(args, **kwargs):
            return _Proc(args, _timeout=True, **kwargs)

        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            self.assertFalse(kwargs.get("shell", False))
            return subprocess.CompletedProcess(argv, 0)

        with mock.patch("trinity_cli.runner.os.name", "nt"), mock.patch(
            "trinity_cli.runner.subprocess.Popen", popen
        ), mock.patch("trinity_cli.runner.subprocess.run", run), mock.patch(
            "trinity_cli.runner.subprocess.CREATE_NEW_PROCESS_GROUP", 0x200, create=True
        ), mock.patch("trinity_cli.runner.npm_shim_target", return_value=None):
            result = Runner().run([r"C:\npm\gbot.cmd", "bots", "list"], timeout=1)
        self.assertTrue(result.timed_out)
        self.assertEqual(result.code, 124)
        self.assertEqual(calls[0][0][:4], ["taskkill", "/F", "/T", "/PID"])
        self.assertNotIn("start_new_session", calls[0][1])

    def test_posix_timeout_kills_the_child_process(self):
        proc = _Proc(["gbot"], _timeout=True)

        def popen(args, **kwargs):
            return proc

        with mock.patch("trinity_cli.runner.os.name", "posix"), mock.patch(
            "trinity_cli.runner.subprocess.Popen", popen
        ):
            result = Runner().run(["gbot"], timeout=1)
        self.assertTrue(result.timed_out)
        self.assertTrue(proc.killed)

    def test_missing_binary_does_not_spawn(self):
        def popen(*args, **kwargs):
            raise FileNotFoundError

        with mock.patch("trinity_cli.runner.subprocess.Popen", popen):
            result = Runner().run(["missing-tool"])
        self.assertEqual(result.code, 127)

    def test_windows_credential_hint_uses_icacls(self):
        with mock.patch("trinity_cli.seats.muse.os.name", "nt"):
            hint = credential_mode_fix()
        self.assertIn("icacls", hint)
        self.assertIn("$env:USERPROFILE", hint)
        self.assertNotIn("%USERPROFILE%", hint)
        self.assertNotIn("chmod", hint)

    def test_config_and_brief_saved_by_windows_tools_still_load(self):
        import json
        import tempfile
        from pathlib import Path

        from trinity_cli.briefing import run_show
        from trinity_cli.config import load_grok_seats, read_config

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = Path(tmp.name, "config.json")
        body = json.dumps({"grok_seats": [{"name": "writer", "account": "login-a", "bot": "Writer"}]})
        for encoding in ("utf-8-sig", "utf-16"):
            config.write_bytes(body.encode(encoding))
            seats, default = load_grok_seats(read_config(config))
            self.assertEqual((seats[0].name, default), ("writer", "writer"))
        config.write_bytes(b"\x80\x81 not text")
        self.assertEqual(read_config(config), {})
        brief = Path(tmp.name, "brief.md")
        brief.write_bytes("共同背景".encode("utf-16"))
        self.assertIn("共同背景", run_show(brief).text)
        brief.write_bytes("共同背景".encode("cp950"))
        shown = run_show(brief)
        self.assertEqual(shown.code, 1)
        self.assertIn("UTF-8", shown.text)

    def test_posix_credential_hint_uses_chmod(self):
        with mock.patch("trinity_cli.seats.muse.os.name", "posix"):
            self.assertEqual(credential_mode_fix(), "chmod 600 ~/.trinity-cli/muse-credential")

    def test_state_replace_is_atomic_and_has_no_fcntl(self):
        import trinity_cli.state as state

        source = inspect.getsource(state)
        self.assertIn("os.replace", source)
        self.assertNotIn("fcntl", source)
        self.assertIn("Path.home()", source)

    def test_text_output_shows_home_as_tilde(self):
        import tempfile
        from pathlib import Path

        from trinity_cli.briefing import run_show
        from trinity_cli.state import tilde

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        fake_home = Path(tmp.name, "someone")
        with mock.patch("trinity_cli.state.Path.home", return_value=fake_home):
            brief = fake_home / ".trinity-cli" / "brief.md"
            self.assertEqual(tilde(brief), str(Path("~", ".trinity-cli", "brief.md")))
            self.assertEqual(tilde(Path(tmp.name, "elsewhere")), str(Path(tmp.name, "elsewhere")))
            shown = run_show(brief)
        self.assertNotIn("someone", shown.text)
        self.assertIn(str(Path("~", ".trinity-cli", "brief.md")), shown.text)
        self.assertIn("brief init", shown.text)
        self.assertEqual(shown.data["path"], str(brief))

    def test_ledger_roundtrip_keeps_unicode_line_separators(self):
        import tempfile
        from pathlib import Path

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        book = Ledger(Path(tmp.name) / "ledger.jsonl")
        book.append({"at": "2026-10-01T00:00:00+00:00", "note": "a\u2028b\u2029c\u0085d研究員"})
        self.assertEqual(book.records(), [{"at": "2026-10-01T00:00:00+00:00", "note": "a\u2028b\u2029c\u0085d研究員"}])
        self.assertNotIn("\n", Path(tmp.name, "ledger.jsonl").read_bytes().decode("utf-8").split("\n")[0])

    def test_concurrent_appends_stay_one_json_line(self):
        import tempfile
        import threading
        import time
        from pathlib import Path

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        book = Ledger(Path(tmp.name) / "ledger.jsonl")

        def slow(handle, payload: bytes) -> None:
            handle.write(payload[:1])
            time.sleep(0.01)
            handle.write(payload[1:])

        def worker(index: int) -> None:
            for n in range(8):
                book.append({"id": f"{index}-{n}", "at": "2026-10-01T00:00:00+00:00"})

        with mock.patch("trinity_cli.state._write_bytes", slow):
            threads = [threading.Thread(target=worker, args=(index,)) for index in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        rows = book.records()
        self.assertEqual(len(rows), 32)
        self.assertEqual({row["id"] for row in rows}, {f"{i}-{n}" for i in range(4) for n in range(8)})

    def test_windows_stdio_is_reconfigured_to_utf8(self):
        stream = mock.Mock()
        with mock.patch("trinity_cli.cli.sys.platform", "win32"), mock.patch(
            "trinity_cli.cli.sys.stdout", stream
        ), mock.patch("trinity_cli.cli.sys.stderr", stream):
            configure_stdio()
        stream.reconfigure.assert_called_with(encoding="utf-8", errors="replace")
        self.assertGreaterEqual(stream.reconfigure.call_count, 2)

    def test_windows_piped_stdin_is_read_as_utf8(self):
        import io

        raw = io.BytesIO("你好".encode("utf-8"))
        piped = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
        with mock.patch("trinity_cli.cli.sys.platform", "win32"), mock.patch(
            "trinity_cli.cli.sys.stdout", mock.Mock()
        ), mock.patch("trinity_cli.cli.sys.stderr", mock.Mock()), mock.patch("trinity_cli.cli.sys.stdin", piped):
            configure_stdio()
        self.assertEqual(piped.read(), "你好")

    def test_posix_stdio_is_left_alone(self):
        stream = mock.Mock()
        with mock.patch("trinity_cli.cli.sys.platform", "darwin"), mock.patch(
            "trinity_cli.cli.sys.stdout", stream
        ), mock.patch("trinity_cli.cli.sys.stderr", stream):
            configure_stdio()
        stream.reconfigure.assert_not_called()


if __name__ == "__main__":
    unittest.main()
