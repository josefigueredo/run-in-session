"""SKILL.md follows the Agent Skills format and names what ris really has."""
from __future__ import annotations

import re
import unittest

from helpers import ROOT
from ris.cli import parser
from skillspec import check_skill

SKILL = (ROOT / "SKILL.md").read_text(encoding="utf-8")


class SkillSpecTest(unittest.TestCase):
    def test_skill_md_conforms_under_its_published_name(self):
        self.assertEqual(check_skill(ROOT, published_name="run-in-session"), [])

    def test_every_ris_command_in_the_skill_exists_in_the_cli(self):
        help_text = parser().format_help()
        for command in ("task", "parse", "claim", "release", "who"):
            self.assertIn(command, help_text)
        for flag in set(re.findall(r"(--[a-z][a-z-]+)", SKILL)):
            self.assertTrue(any(flag in a.option_strings for sub in _all_parsers() for a in sub._actions),
                            f"SKILL.md mentions {flag}, which no ris command has")

    def test_the_exit_codes_in_the_skill_match_the_cli(self):
        from ris import cli
        self.assertIn(f"0 ok, 2 usage, 3 refused (deny pattern or claim), 4 not a message, 5 unsupported version, 6 unknown id", SKILL)
        self.assertEqual((cli.OK, cli.USAGE, cli.REFUSED, cli.INVALID, cli.VERSION, cli.UNKNOWN), (0, 2, 3, 4, 5, 6))


def _all_parsers():
    out, stack = [], [parser()]
    while stack:
        p = stack.pop()
        out.append(p)
        for action in p._actions:
            if hasattr(action, "choices") and isinstance(action.choices, dict):
                stack.extend(action.choices.values())
    return out


if __name__ == "__main__":
    unittest.main()
