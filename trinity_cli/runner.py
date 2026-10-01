"""The only place trinity starts other programs.

Arguments are always a list, never `shell=True`. On Windows, `shutil.which`
returns npm shims such as `gbot.cmd`; trinity runs node on the script behind the
shim, so cmd.exe never parses a message. Other batch files go through
`cmd.exe /d /s /c` with every argument quoted. A timeout kills the child with
`proc.kill()` on POSIX and `taskkill /T` on Windows. Output is decoded as UTF-8.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


# Browser approval and `codex login` wait on a person. Don't capture their output:
# a token printed by the child must stay on the terminal, not in this process.
LOGIN_TIMEOUT = 900


@dataclass
class Proc:
    code: int
    out: str
    err: str
    timed_out: bool = False


# npm's cmd-shim ends with `"%_prog%" "%dp0%\node_modules\<pkg>\bin\<tool>.js" %*`.
_NPM_SHIM_SCRIPT = re.compile(r'"%~?dp0%?\\([^"]+\.[cm]?js)"', re.IGNORECASE)
# cmd.exe expands %VAR% and ends the line at a newline even inside quotes.
_CMD_UNSAFE = ('"', "%", "\r", "\n")


class UnsafeCommand(ValueError):
    pass


def npm_shim_target(shim: str) -> list[str] | None:
    """node and the script behind an npm .cmd shim, so cmd.exe never parses the arguments."""
    try:
        text = Path(shim).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = _NPM_SHIM_SCRIPT.search(text)
    if not match:
        return None
    base = Path(shim).parent
    script = base.joinpath(*match.group(1).split("\\"))
    if not script.is_file():
        return None
    local = base / "node.exe"
    node = str(local) if local.is_file() else shutil.which("node")
    return [node, str(script)] if node else None


def _cmd_quote(arg: str) -> str:
    # Backslashes before the closing quote are doubled so the child's argv parser keeps them.
    return '"' + re.sub(r"(\\+)$", r"\1\1", arg) + '"'


def command_argv(argv: list[str]) -> list[str] | str:
    """Keep Windows batch shims runnable without shell=True."""
    if os.name == "nt" and argv and argv[0].lower().endswith((".cmd", ".bat")):
        direct = npm_shim_target(argv[0])
        if direct:
            return [*direct, *argv[1:]]
        if any(ch in arg for arg in argv for ch in _CMD_UNSAFE):
            raise UnsafeCommand(f"{os.path.basename(argv[0])} 是 .cmd 檔，cmd.exe 無法安全傳遞含引號、% 或換行的參數")
        comspec = os.environ.get("COMSPEC") or "cmd.exe"
        # /s strips only the outer pair of quotes, the same line Node builds for .cmd files.
        return f'"{comspec}" /d /s /c "{" ".join(_cmd_quote(arg) for arg in argv)}"'
    return list(argv)


def _pop_kwargs() -> dict:
    kwargs = {"shell": False}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return kwargs


def _terminate(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
            shell=False,
        )
        return
    proc.kill()


class Runner:
    def run(
        self,
        argv: list[str],
        *,
        stdin: str | None = None,
        timeout: float = 60.0,
        env: dict | None = None,
    ) -> Proc:
        name = os.path.basename(argv[0]) if argv else "command"
        try:
            command = command_argv(argv)
        except UnsafeCommand as exc:
            return Proc(2, "", str(exc))
        try:
            proc = subprocess.Popen(
                command,
                stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                **_pop_kwargs(),
            )
        except FileNotFoundError:
            return Proc(127, "", f"{name}: not found")
        try:
            out, err = proc.communicate(input=stdin, timeout=timeout)
        except subprocess.TimeoutExpired:
            _terminate(proc)
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
            return Proc(124, "", f"{name} timed out after {timeout:.0f}s", timed_out=True)
        return Proc(proc.returncode or 0, out or "", err or "")

    def attach(self, argv: list[str], *, timeout: float = LOGIN_TIMEOUT) -> Proc:
        """Run with the caller's terminal. stdout and stderr are not captured."""
        try:
            proc = subprocess.Popen(command_argv(argv), **_pop_kwargs())
        except UnsafeCommand as exc:
            return Proc(2, "", str(exc))
        except FileNotFoundError:
            return Proc(127, "", "")
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _terminate(proc)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            return Proc(124, "", "", timed_out=True)
        return Proc(code, "", "")


def find_tool(name: str, env_var: str, fallbacks: tuple[str, ...] = ()) -> str | None:
    override = os.environ.get(env_var)
    if override:
        return os.path.expanduser(override)
    found = shutil.which(name)
    if found:
        return found
    for pattern in fallbacks:
        matches = sorted(glob.glob(os.path.expanduser(pattern)))
        if matches:
            return matches[-1]
    return None


def env_with_tool_dir(binary: str) -> dict:
    """gbot is `#!/usr/bin/env node`; keep its node reachable when PATH is minimal."""
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(binary) + os.pathsep + env.get("PATH", "")
    return env
