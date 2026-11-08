"""Help text and docs stay aligned with the real parser."""

import re
import tomllib
import unittest
from pathlib import Path

from trinity_cli import __version__
from trinity_cli.cli import build_parser
from trinity_cli.seats.muse import FIX_TOKEN

ROOT = Path(__file__).resolve().parents[1]
# English: README.md + docs/reference.md. 中文：README.zh-TW.md + docs/reference.zh-TW.md.
LANGUAGES = {
    "en": ("README.md", "docs/reference.md"),
    "zh-TW": ("README.zh-TW.md", "docs/reference.zh-TW.md"),
}
DOCS = {lang: tuple((ROOT / name).read_text(encoding="utf-8") for name in names) for lang, names in LANGUAGES.items()}
ALL_DOCS = tuple(text for pair in DOCS.values() for text in pair)
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
            self._assert_documented(name)
            self.assertIn(name, SKILL, name)
            for action in sub._actions:
                if action.help is None or action.dest == "help":
                    continue
                self.assertTrue(str(action.help).strip(), f"{name} {action.dest}")
        brief = choices["brief"]
        nested = next(action for action in brief._actions if action.dest == "brief_command")
        for name, sub in nested.choices.items():
            self.assertTrue((sub.description or "").strip(), name)
            self._assert_documented(name)
            self.assertIn(name, SKILL, name)
        grok = choices["grok"]
        grok_nested = next(action for action in grok._actions if action.dest == "grok_command")
        self.assertEqual(set(grok_nested.choices), {"bots", "add", "remove"})
        for name, sub in grok_nested.choices.items():
            self.assertTrue((sub.description or "").strip(), name)
            self._assert_documented(name)
            self.assertIn(name, SKILL, name)

    def _assert_documented(self, name):
        for lang, texts in DOCS.items():
            for path, text in zip(LANGUAGES[lang], texts):
                self.assertIn(name, text, f"{name} in {path}")

    def test_wait_help_names_the_default_grok_seat(self):
        wait = _commands(build_parser())["wait"]
        spec = next(action for action in wait._actions if action.dest == "spec")
        self.assertIn("default Grok seat", spec.help or "")
        self.assertNotIn("grok_bot", spec.help or "")
        for text in ALL_DOCS:
            self.assertNotIn("單獨 `grok` 用 `grok_bot`", text)
            self.assertNotIn("bare `grok` uses `grok_bot`", text)
        self.assertIn("`grok`（預設座位）", DOCS["zh-TW"][1])
        self.assertIn("`grok` (the default Grok seat)", DOCS["en"][1])

    def test_help_examples_include_the_common_flows(self):
        text = build_parser().format_help()
        for snippet in ("status", "digest", "ask all", "hand ", "wait ", "schedules", "who ", "brief ", "log ", "login "):
            self.assertIn(snippet, text)

    def test_family_urls_are_in_the_readme_and_skill(self):
        for lang, (readme, _reference) in DOCS.items():
            for url in URLS:
                self.assertIn(url, readme, f"{lang} {url}")
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
        pin_line = {"en": f"v{version} pins these versions", "zh-TW": f"v{version} 釘這些版本"}
        for tool in ("trinity-cli", "muse-web-cli", "chatgpt-dot-cli"):
            pins = set(re.findall(rf"{tool}\.git@v([^\"\s]+)", "\n".join(ALL_DOCS)))
            self.assertEqual(len(pins), 1, f"{tool} {sorted(pins)}")
            self.assertIn(f"{tool} v{next(iter(pins))}", ci, tool)
        for lang, (readme, reference) in DOCS.items():
            with self.subTest(lang=lang):
                for tool in ("trinity-cli", "muse-web-cli", "chatgpt-dot-cli"):
                    self.assertEqual(len(set(re.findall(rf"{tool}\.git@v([^\"\s]+)", readme))), 1, tool)
                self.assertEqual(set(re.findall(r"trinity-cli\.git@v([^\"\s]+)", readme)), {version})
                self.assertEqual(readme.count(pin_line[lang]), 1)
                self.assertNotIn(pin_line[lang], reference)
                for text in (readme, reference):
                    self.assertNotIn("Node 18+", text)
                    self.assertNotIn("github.com/ImL1s/grok-bot-cli", text)
                    self.assertNotIn("npm install -g \"git+https://gitlab.com/aa22396584/grok-bot-cli", text)
                self.assertIn("22.19.0", readme)
                self.assertGreaterEqual(readme.count("grok-bot-cli-0.11.2.tgz"), 4)
                self.assertIn("FORK.md#install", readme)

    def test_docs_say_login_muse_stores_the_gateway_token(self):
        for text in (DOCS["en"][0], DOCS["zh-TW"][0], SKILL):
            self.assertIn("~/.trinity-cli/muse-credential", text)
            self.assertIn("mode 600", text)
        for stale in ("不印、不複製憑證", "does not print or copy a credential", "不讀、不印 token"):
            for text in ALL_DOCS:
                self.assertNotIn(stale, text)
        self.assertNotIn("不讀、不印 token", FIX_TOKEN)
        self.assertIn("mode 600", FIX_TOKEN)


if __name__ == "__main__":
    unittest.main()
