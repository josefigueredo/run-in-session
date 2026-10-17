"""The task and reply messages: what the sender renders is what the receiver parses, inside whatever wraps it."""
from __future__ import annotations

import unittest

from helpers import ROOT  # noqa: F401  (puts the repo on sys.path)
from ris import formats
from ris.formats import FormatError, Reply, Task, UnsupportedVersion

TASK = Task(id="20261017-114312-a1b2", sender="bugs", to="main-session", goal="Rebase feat/mcp-integration on fix/20",
            done_when="the branch merges with no conflicts and its tests pass", touches=["feat/mcp-integration"],
            forbidden=["push", "open PRs"], context="fix/20 adds the missing END; to migration 0018.\nIt is pushed.")


class TaskFormatTest(unittest.TestCase):
    def test_the_first_line_says_who_asks_what_on_its_own(self):
        first = formats.render_task(TASK).splitlines()[0]
        self.assertEqual(first, "ris task from bugs: Rebase feat/mcp-integration on fix/20 [a1b2]")

    def test_a_rendered_task_parses_back_to_the_same_task(self):
        self.assertEqual(formats.parse(formats.render_task(TASK)), TASK)

    def test_it_parses_inside_the_wrapper_the_channel_adds(self):
        wrapped = ('Another Claude session sent a message:\n<cross-session-message from="uds:/tmp/x.sock" from-name="bugs">\n'
                   + formats.render_task(TASK) + "\n</cross-session-message>\n")
        self.assertEqual(formats.parse(wrapped), TASK)

    def test_empty_lists_and_context_round_trip(self):
        bare = Task(id="1", sender="a", to="b", goal="g", done_when="d")
        self.assertEqual(formats.parse(formats.render_task(bare)), bare)

    def test_a_field_with_a_line_break_is_refused_when_rendering(self):
        with self.assertRaises(FormatError):
            formats.render_task(Task(id="1", sender="a", to="b", goal="two\nlines", done_when="d"))

    def test_a_list_item_with_a_semicolon_is_refused_because_it_would_split(self):
        with self.assertRaises(FormatError):
            formats.render_task(Task(id="1", sender="a", to="b", goal="g", done_when="d", touches=["a; b"]))

    def test_a_task_without_goal_is_invalid(self):
        text = formats.render_task(TASK).replace("goal: Rebase feat/mcp-integration on fix/20\n", "")
        with self.assertRaises(FormatError):
            formats.parse(text)

    def test_a_task_without_its_end_marker_is_invalid(self):
        text = formats.render_task(TASK).replace("--- end ris-task ---", "")
        with self.assertRaises(FormatError):
            formats.parse(text)

    def test_text_with_no_marker_is_not_a_message(self):
        with self.assertRaises(FormatError):
            formats.parse("hola, ¿me rebaseás MCP?")

    def test_an_unknown_optional_field_is_ignored_so_old_parsers_keep_reading(self):
        text = formats.render_task(TASK).replace("--- context ---", "priority: high\n--- context ---")
        self.assertEqual(formats.parse(text), TASK)

    def test_a_line_that_is_not_a_field_is_invalid(self):
        text = formats.render_task(TASK).replace("--- context ---", "this is not a field\n--- context ---")
        with self.assertRaises(FormatError):
            formats.parse(text)

    def test_an_unknown_version_is_reported_as_such(self):
        text = formats.render_task(TASK).replace("ris-task v1", "ris-task v2")
        with self.assertRaises(UnsupportedVersion):
            formats.parse(text)


REPLY = Reply(id="20261017-114312-a1b2", sender="main-session", status="done", summary="Rebased, 0 conflicts",
              evidence=["git log --oneline -1: 1a2b3c4d", "npx vitest run: 412 passed"], pending=["push is yours"])


class WhenTest(unittest.TestCase):
    def test_a_task_without_when_renders_no_when_line_and_reads_as_now(self):
        text = formats.render_task(TASK)
        self.assertNotIn("\nwhen:", text)
        self.assertEqual(formats.parse(text).when, "now")

    def test_after_current_round_trips_and_an_unknown_value_is_refused(self):
        task = Task(id="1", sender="a", to="b", goal="g", done_when="d", when="after-current")
        text = formats.render_task(task)
        self.assertIn("\nwhen: after-current\n", text)
        self.assertEqual(formats.parse(text).when, "after-current")
        with self.assertRaises(formats.FormatError):
            formats.render_task(Task(id="1", sender="a", to="b", goal="g", done_when="d", when="later"))
        with self.assertRaises(formats.FormatError):
            formats.parse(text.replace("when: after-current", "when: later"))


class ReplyFormatTest(unittest.TestCase):
    def test_the_first_line_carries_id_status_and_summary(self):
        self.assertEqual(formats.render_reply(REPLY).splitlines()[0],
                         "ris reply from main-session (done): Rebased, 0 conflicts [a1b2]")

    def test_a_rendered_reply_parses_back(self):
        self.assertEqual(formats.parse(formats.render_reply(REPLY)), REPLY)

    def test_evidence_items_may_contain_semicolons(self):
        reply = Reply(id="1", sender="a", status="partial", summary="s", evidence=["a; b"])
        self.assertEqual(formats.parse(formats.render_reply(reply)), reply)

    def test_an_unknown_status_is_refused(self):
        with self.assertRaises(FormatError):
            formats.render_reply(Reply(id="1", sender="a", status="maybe", summary="s"))
        text = formats.render_reply(REPLY).replace("status: done", "status: maybe")
        with self.assertRaises(FormatError):
            formats.parse(text)


if __name__ == "__main__":
    unittest.main()
