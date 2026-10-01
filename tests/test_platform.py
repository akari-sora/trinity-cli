"""Windows branches. These tests never start a real child process."""

import inspect
import subprocess
import unittest
from unittest import mock

from trinity_cli.cli import configure_stdio
from trinity_cli.runner import Runner, command_argv, find_tool
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
        ) as which:
            found = find_tool("gbot", "TRINITY_GBOT_UNSET")
            wrapped = command_argv([found, "--json", "bots", "list"])
        which.assert_called_once_with("gbot")
        self.assertEqual(found, shim)
        self.assertEqual(wrapped[1:4], ["/d", "/s", "/c"])
        self.assertEqual(wrapped[4:], [shim, "--json", "bots", "list"])
        self.assertNotIn(True, wrapped)

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
        ):
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
        self.assertNotIn("chmod", hint)

    def test_posix_credential_hint_uses_chmod(self):
        with mock.patch("trinity_cli.seats.muse.os.name", "posix"):
            self.assertEqual(credential_mode_fix(), "chmod 600 ~/.trinity-cli/muse-credential")

    def test_state_replace_is_atomic_and_has_no_fcntl(self):
        import trinity_cli.state as state

        source = inspect.getsource(state)
        self.assertIn("os.replace", source)
        self.assertNotIn("fcntl", source)
        self.assertIn("Path.home()", source)

    def test_windows_stdio_is_reconfigured_to_utf8(self):
        stream = mock.Mock()
        with mock.patch("trinity_cli.cli.sys.platform", "win32"), mock.patch(
            "trinity_cli.cli.sys.stdout", stream
        ), mock.patch("trinity_cli.cli.sys.stderr", stream):
            configure_stdio()
        stream.reconfigure.assert_called_with(encoding="utf-8", errors="replace")
        self.assertGreaterEqual(stream.reconfigure.call_count, 2)

    def test_posix_stdio_is_left_alone(self):
        stream = mock.Mock()
        with mock.patch("trinity_cli.cli.sys.platform", "darwin"), mock.patch(
            "trinity_cli.cli.sys.stdout", stream
        ), mock.patch("trinity_cli.cli.sys.stderr", stream):
            configure_stdio()
        stream.reconfigure.assert_not_called()


if __name__ == "__main__":
    unittest.main()
