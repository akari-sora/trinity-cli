"""The real muse-web-cli binary that README pins. Skipped unless TRINITY_MUSE_CONTRACT=1.

Every call runs with HOME and USERPROFILE pointed at a throwaway directory and
`--backend api`, so it never starts Chrome, never reaches Muse, and never sees the
real ~/.trinity-cli/muse-credential. The credential files written here are fake.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trinity_cli.seats.muse import MuseSeat

ROOT = Path(__file__).resolve().parents[1]
ENABLED = os.environ.get("TRINITY_MUSE_CONTRACT") == "1"
FAKE_CREDENTIAL = {"base_url": "https://hatch.metaaivm.com", "auth": {"type": "bearer"}, "vm_id": "vm-fake"}


def _pin() -> str:
    pins = set(re.findall(r"muse-web-cli\.git@v([^\"\s]+)", (ROOT / "README.md").read_text(encoding="utf-8")))
    if len(pins) != 1:
        raise AssertionError(f"README pins more than one muse-web-cli version: {sorted(pins)}")
    return pins.pop()


def _binary() -> str:
    found = os.environ.get("TRINITY_MUSE_CLI") or shutil.which("muse-web-cli")
    if not found:
        raise AssertionError("muse-web-cli is not installed; set TRINITY_MUSE_CLI")
    return found


@unittest.skipUnless(ENABLED, "set TRINITY_MUSE_CONTRACT=1 to run against the installed muse-web-cli")
class MuseWebCliContractTests(unittest.TestCase):
    def setUp(self):
        self.binary = _binary()
        self.home = Path(tempfile.mkdtemp(prefix="trinity-muse-contract-"))
        self.addCleanup(shutil.rmtree, self.home, True)
        env = {key: value for key, value in os.environ.items() if not key.startswith("MUSE_WEB_")}
        env.update(HOME=str(self.home), USERPROFILE=str(self.home), PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD="1")
        self.env = env

    def _cli(self, *args):
        return subprocess.run(
            [self.binary, *args], env=self.env, capture_output=True, text=True, encoding="utf-8", timeout=60
        )

    def _api_status(self):
        proc = self._cli("--json", "--autostart", "--backend", "api", "status")
        return proc.returncode, json.loads(proc.stdout)

    def _write_credential(self, mode: int):
        folder = self.home / ".trinity-cli"
        folder.mkdir(mode=0o700, exist_ok=True)
        path = folder / "muse-credential"
        path.write_text(json.dumps(FAKE_CREDENTIAL), encoding="utf-8")
        os.chmod(path, mode)

    def test_version_matches_the_readme_pin(self):
        proc = self._cli("--version")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), f"muse-web-cli {_pin()}")

    def test_help_has_credential_and_backend(self):
        proc = self._cli("--help")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("credential", proc.stdout)
        self.assertIn("--backend", proc.stdout)
        self.assertIn("muse-credential", proc.stdout)

    def test_missing_credential_is_exit_4_and_does_not_start_chrome(self):
        code, payload = self._api_status()
        self.assertEqual(code, 4)
        self.assertEqual(payload["state"], "unsupported")
        self.assertEqual(payload["backend"], "api")
        self.assertIn("muse-credential", payload["error"])
        self.assertFalse((self.home / ".trinity-cli" / "muse-profile").exists())

    def test_credential_without_a_token_is_not_exit_4(self):
        self._write_credential(0o600)
        code, payload = self._api_status()
        self.assertEqual(code, 3)
        self.assertNotEqual(payload["state"], "unsupported")

    @unittest.skipIf(os.name == "nt", "POSIX file modes")
    def test_readable_credential_is_refused(self):
        self._write_credential(0o644)
        code, payload = self._api_status()
        self.assertEqual(code, 2)
        self.assertEqual(payload["state"], "credential_permissions")

    def test_seat_reports_missing_credential_as_unsupported(self):
        with mock.patch.dict(os.environ, self.env, clear=True):
            result = MuseSeat(binary=self.binary, token_binary="", backend="api").status()
        self.assertEqual(result.state, "unsupported")
        self.assertIn("muse-credential", result.error)

    @unittest.skipIf(os.name == "nt", "POSIX file modes")
    def test_seat_gives_the_mode_fix_for_a_readable_credential(self):
        self._write_credential(0o644)
        with mock.patch.dict(os.environ, self.env, clear=True):
            result = MuseSeat(binary=self.binary, token_binary="", backend="api").status()
        self.assertEqual(result.state, "failed")
        self.assertIn("chmod 600", result.hint)


if __name__ == "__main__":
    unittest.main()
