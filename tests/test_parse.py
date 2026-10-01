"""README examples must parse on Python 3.11, where options cannot follow a nargs='*' positional."""

import unittest

from trinity_cli.cli import build_parser


class ParseExamples(unittest.TestCase):
    def parse(self, argv):
        return build_parser().parse_args(argv)

    def test_hand_option_between_positionals(self):
        args = self.parse(["hand", "dot#last", "--to", "grok:example-bot", "請看這則"])
        self.assertEqual(args.source, "dot#last")
        self.assertEqual(args.dest, "grok:example-bot")
        self.assertEqual(args.instruction, ["請看這則"])

    def test_ask_grok_bot_and_account_before_text(self):
        args = self.parse(["ask", "grok", "--bot", "Other", "--account", "example-login", "hello"])
        self.assertEqual(args.seat, "grok")
        self.assertEqual(args.bot, "Other")
        self.assertEqual(args.account, "example-login")
        self.assertEqual(args.words, ["hello"])

    def test_ask_all_text(self):
        args = self.parse(["ask", "all", "今天進度？"])
        self.assertEqual(args.words, ["今天進度？"])

    def test_wait_then_hand_keeps_the_remainder(self):
        args = self.parse(
            ["wait", "dot", "--timeout", "5", "--then", "hand", "dot#last", "--to", "grok", "--yes", "接著"]
        )
        self.assertEqual(args.then, ["hand", "dot#last", "--to", "grok", "--yes", "接著"])


if __name__ == "__main__":
    unittest.main()
