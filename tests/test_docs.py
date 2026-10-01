"""Help text and docs stay aligned with the real parser."""

import unittest
from pathlib import Path

from trinity_cli.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
SKILL = (ROOT / "skills" / "trinity-cli" / "SKILL.md").read_text(encoding="utf-8")
URLS = (
    "https://gitlab.com/aa22396584/trinity-cli",
    "https://gitlab.com/aa22396584/chatgpt-dot-cli",
    "https://gitlab.com/aa22396584/grok-bot-cli",
    "https://github.com/ImL1s/grok-bot-cli",
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


if __name__ == "__main__":
    unittest.main()
