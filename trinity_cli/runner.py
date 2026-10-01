"""The only place trinity starts other programs."""

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


class Runner:
    def run(
        self,
        argv: list[str],
        *,
        stdin: str | None = None,
        timeout: float = 60.0,
        env: dict | None = None,
    ) -> Proc:
        try:
            done = subprocess.run(
                argv,
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=env,
                stdin=None if stdin is not None else subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return Proc(127, "", f"{os.path.basename(argv[0])}: not found")
        except subprocess.TimeoutExpired:
            return Proc(124, "", f"{os.path.basename(argv[0])} timed out after {timeout:.0f}s", timed_out=True)
        return Proc(done.returncode, done.stdout or "", done.stderr or "")

    def attach(self, argv: list[str], *, timeout: float = LOGIN_TIMEOUT) -> Proc:
        """Run with the caller's terminal. stdout and stderr are not captured."""
        try:
            done = subprocess.run(argv, timeout=timeout)
        except FileNotFoundError:
            return Proc(127, "", "")
        except subprocess.TimeoutExpired:
            return Proc(124, "", "", timed_out=True)
        return Proc(done.returncode, "", "")


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
