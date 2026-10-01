"""The only place trinity starts other programs.

Arguments are always a list, never `shell=True`. On Windows, `shutil.which`
returns npm shims such as `gbot.cmd`; those are started with `cmd.exe /d /s /c`
so CreateProcess can run them. A timeout kills the child with `proc.kill()` on
POSIX and `taskkill /T` on Windows. Output is decoded as UTF-8.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
from dataclasses import dataclass


# Browser approval and `codex login` wait on a person. Don't capture their output:
# a token printed by the child must stay on the terminal, not in this process.
LOGIN_TIMEOUT = 900


@dataclass
class Proc:
    code: int
    out: str
    err: str
    timed_out: bool = False


def command_argv(argv: list[str]) -> list[str]:
    """Keep Windows batch shims runnable without shell=True."""
    if os.name == "nt" and argv and argv[0].lower().endswith((".cmd", ".bat")):
        comspec = os.environ.get("COMSPEC") or "cmd.exe"
        return [comspec, "/d", "/s", "/c", *argv]
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
            proc = subprocess.Popen(
                command_argv(argv),
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
