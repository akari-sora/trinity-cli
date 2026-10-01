"""Help text and docs stay aligned with the real parser."""

import re
import tomllib
import unittest
from pathlib import Path

from trinity_cli import __version__
from trinity_cli.cli import build_parser
from trinity_cli.seats.muse import FIX_TOKEN

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
SKILL = (ROOT / "skills" / "trinity-cli" / "SKILL.md").read_text(encoding="utf-8")
URLS = (
    "https://gitlab.com/aa22396584/trinity-cli",
    "https://gitlab.com/aa22396584/chatgpt-dot-cli",
    "https://gitlab.com/aa22396584/grok-bot-cli",
    "https://gitlab.com/aa22396584/muse-web-cli",
)


def _commands(parser):
    sub = next(action for action in parser._actions if action.dest == "command")
    return sub.choices


class DocsDriftTests(unittest.TestCase):
    def test_every_command_has_help_and_is_documented(self):
        parser = build_parser()
        choices = _commands(parser)
        self.assertGreaterEqual(set(choices), {"status", "digest", "ask", "hand", "wait", "schedules", "who", "brief", "log", "login"})
        for name, sub in choices.items():
            self.assertTrue(sub.description or sub.format_help().strip(), name)
            self.assertIn(name, README, name)
            self.assertIn(name, SKILL, name)
            for action in sub._actions:
                if action.help is None or action.dest == "help":
                    continue
                self.assertTrue(str(action.help).strip(), f"{name} {action.dest}")
        brief = choices["brief"]
        nested = next(action for action in brief._actions if action.dest == "brief_command")
        for name, sub in nested.choices.items():
            self.assertTrue((sub.description or "").strip(), name)
            self.assertIn(name, README, name)
            self.assertIn(name, SKILL, name)
        grok = choices["grok"]
        grok_nested = next(action for action in grok._actions if action.dest == "grok_command")
        self.assertEqual(set(grok_nested.choices), {"bots", "add", "remove"})
        for name, sub in grok_nested.choices.items():
            self.assertTrue((sub.description or "").strip(), name)
            self.assertIn(name, README, name)
            self.assertIn(name, SKILL, name)

    def test_help_examples_include_the_common_flows(self):
        text = build_parser().format_help()
        for snippet in ("status", "digest", "ask all", "hand ", "wait ", "schedules", "who ", "brief ", "log ", "login "):
            self.assertIn(snippet, text)

    def test_family_urls_are_in_the_readme_and_skill(self):
        for url in URLS:
            self.assertIn(url, README, url)
        self.assertIn("chatgpt-dot-cli", SKILL)
        self.assertIn("muse-web-cli", SKILL)
        self.assertIn("gbot --help", SKILL)

    def test_version_pins_agree_across_readme_ci_and_changelog(self):
        version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        self.assertEqual(__version__, version)
        lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
        self.assertIn(f'name = "trinity-cli"\nversion = "{version}"', lock)
        newest = re.search(r"^## (\S+)", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)
        self.assertEqual(newest.group(1), version)
        ci = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
        for tool in ("trinity-cli", "muse-web-cli", "chatgpt-dot-cli"):
            pins = set(re.findall(rf"{tool}\.git@v([^\"\s]+)", README))
            self.assertEqual(len(pins), 1, f"{tool} {sorted(pins)}")
            self.assertIn(f"{tool} v{next(iter(pins))}", ci, tool)
        self.assertEqual(set(re.findall(r"trinity-cli\.git@v([^\"\s]+)", README)), {version})
        self.assertEqual(README.count(f"v{version} 釘這些版本"), 1)
        self.assertEqual(README.count(f"v{version} pins these versions"), 1)
        self.assertNotIn("Node 18+", README)
        self.assertIn("22.19.0", README)
        self.assertNotIn("github.com/ImL1s/grok-bot-cli", README)
        self.assertNotIn("npm install -g \"git+https://gitlab.com/aa22396584/grok-bot-cli", README)
        self.assertGreaterEqual(README.count("grok-bot-cli-0.11.2.tgz"), 4)
        self.assertIn("FORK.md#install", README)

    def test_docs_say_login_muse_stores_the_gateway_token(self):
        for text in (README, SKILL):
            self.assertIn("~/.trinity-cli/muse-credential", text)
            self.assertIn("mode 600", text)
        for stale in ("不印、不複製憑證", "does not print or copy a credential", "不讀、不印 token"):
            self.assertNotIn(stale, README)
        self.assertNotIn("不讀、不印 token", FIX_TOKEN)
        self.assertIn("mode 600", FIX_TOKEN)


if __name__ == "__main__":
    unittest.main()
