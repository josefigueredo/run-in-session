"""The docs tell the truth: links land, the format examples parse, and every exit code and log event is documented."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from helpers import ROOT
from ris import cli, formats

DOCS = ROOT / "docs"
FORMATOS = (DOCS / "formatos.md").read_text(encoding="utf-8")
PAGES = [ROOT / "README.md", *sorted(DOCS.glob("*.md"))]


def slug(heading: str) -> str:
    text = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return text.replace(" ", "-")


def anchors(path: Path) -> set:
    return {slug(m.group(2)) for m in re.finditer(r"^(#{1,6}) (.+)$", path.read_text(encoding="utf-8"), re.M)}


def blocks(lang: str) -> list:
    return re.findall(rf"```{lang}\n(.*?)```", FORMATOS, re.S)


class DocsTest(unittest.TestCase):
    def test_every_relative_link_lands_on_a_file_and_an_anchor(self):
        link = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
        for page in PAGES:
            for target in link.findall(page.read_text(encoding="utf-8")):
                if re.match(r"[a-z]+:", target):
                    continue
                path, _, fragment = target.partition("#")
                dest = (page.parent / path).resolve() if path else page
                self.assertTrue(dest.exists(), f"{page.name} links to {target}, which does not exist")
                if fragment and dest.suffix == ".md":
                    self.assertIn(fragment, anchors(dest), f"{page.name} links to {target}: no such heading")

    def test_the_task_and_reply_examples_are_what_ris_renders(self):
        task, reply = blocks("text")[:2]  # the third is the terminal marks
        self.assertEqual(formats.render_task(formats.parse(task)), task)
        self.assertEqual(formats.render_reply(formats.parse(reply)), reply)

    def test_the_log_example_lines_are_json_with_documented_events(self):
        [example] = blocks("json")[:1]
        for line in example.strip().splitlines():
            self.assertIn(json.loads(line)["event"], FORMATOS)
        for event in ("sent", "received", "replied", "reply-received"):
            self.assertIn(f"| `{event}` |", FORMATOS)

    def test_every_exit_code_has_a_row(self):
        for code in (cli.OK, cli.USAGE, cli.REFUSED, cli.INVALID, cli.VERSION, cli.UNKNOWN):
            self.assertRegex(FORMATOS, rf"\n\| {code} \| ")

    def test_every_documented_log_command_passes_its_session_ref(self):
        # task list, task show, task reply and parse read or write one session's log: without --as they exit 2.
        # A runnable command is a python3 line or one with flags; a bare `ris parse` in prose is just the name.
        command = re.compile(r"^python3 .*|ris(?:\.py)? (?:task (?:list|show|reply)|parse)\b[^`\n]*--[^`\n]*", re.M)
        for path in (ROOT / "SKILL.md", *PAGES):
            for cmd in command.findall(path.read_text("utf-8")):
                if re.search(r"ris(?:\.py)? (?:task (?:list|show|reply)|parse)\b", cmd):
                    self.assertIn("--as", cmd, f"{path.name}: {cmd}")

    def test_every_status_is_documented(self):
        for status in formats.STATUSES:
            self.assertIn(f"`{status}`", FORMATOS)


if __name__ == "__main__":
    unittest.main()
