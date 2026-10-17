"""ris as the agent runs it: render, parse, log and claims, with their exit codes."""
from __future__ import annotations

import json
import re
import subprocess
import unittest

from helpers import make_dir, run_cli

NEW = ["task", "new", "--from", "bugs", "--to", "main-session", "--to-ref", "248292",
       "--goal", "Rebase feat/mcp-integration on fix/20", "--done", "merges clean and tests pass",
       "--touch", "feat/mcp-integration", "--forbid", "push"]


def log(home) -> list:
    path = home / "log.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class TaskNewTest(unittest.TestCase):
    def test_it_prints_the_message_and_logs_it_as_sent_with_the_peer_ref(self):
        home = make_dir()
        out = run_cli(NEW + ["--context", "fix/20 is pushed"], home)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertRegex(out.stdout.splitlines()[0], r"^ris task \d{8}-\d{6}-[0-9a-f]{4} from bugs: Rebase")
        self.assertIn("fix/20 is pushed", out.stdout)
        [entry] = log(home)
        self.assertEqual((entry["event"], entry["peer"], entry["peer_ref"]), ("sent", "main-session", "248292"))
        self.assertEqual(entry["goal"], "Rebase feat/mcp-integration on fix/20")

    def test_context_can_come_from_stdin(self):
        home = make_dir()
        out = run_cli(NEW + ["--context", "-"], home, stdin="line one\nline two\n")
        self.assertIn("line one\nline two\n--- end ris-task ---", out.stdout)

    def test_a_deny_pattern_that_matches_refuses_before_logging(self):
        home = make_dir()
        out = run_cli(NEW + ["--context", "then git push origin", "--deny", r"git\s+push"], home)
        self.assertEqual(out.returncode, 3)
        self.assertIn("git\\s+push", out.stderr)
        self.assertEqual(out.stdout, "")
        self.assertEqual(log(home), [])

    def test_a_goal_on_two_lines_is_a_usage_error(self):
        out = run_cli(["task", "new", "--from", "a", "--to", "b", "--goal", "x\ny", "--done", "d"], make_dir())
        self.assertEqual(out.returncode, 2)


class ParseTest(unittest.TestCase):
    def _task_text(self, home) -> str:
        return run_cli(NEW, home).stdout

    def test_a_received_task_prints_json_and_is_logged_from_its_sender(self):
        sender, receiver = make_dir(), make_dir()
        text = "Another Claude session sent a message:\n" + self._task_text(sender)
        out = run_cli(["parse"], receiver, stdin=text)
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual((data["kind"], data["from"], data["goal"]), ("task", "bugs", "Rebase feat/mcp-integration on fix/20"))
        [entry] = log(receiver)
        self.assertEqual((entry["event"], entry["peer"]), ("received", "bugs"))

    def test_a_reply_to_a_task_we_sent_closes_it(self):
        sender, receiver = make_dir(), make_dir()
        task_id = json.loads(run_cli(["parse"], receiver, stdin=self._task_text(sender)).stdout)["id"]
        reply = run_cli(["task", "reply", task_id, "--from", "main-session", "--status", "done",
                         "--summary", "Rebased", "--evidence", "git log -1: abc"], receiver).stdout
        out = run_cli(["parse"], sender, stdin=reply)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout)["status"], "done")
        self.assertEqual(run_cli(["task", "list", "--open"], sender).stdout.strip(), "no open tasks")

    def test_a_reply_whose_id_we_never_sent_is_flagged(self):
        receiver, stranger = make_dir(), make_dir()
        reply = run_cli(["task", "reply", "20990101-000000-ffff", "--from", "x", "--status", "done", "--summary", "s"],
                        receiver).stdout
        out = run_cli(["parse"], stranger, stdin=reply)
        self.assertEqual(out.returncode, 6)
        self.assertIn("not in this log", out.stderr)
        self.assertEqual(json.loads(out.stdout)["id"], "20990101-000000-ffff")

    def test_text_with_no_message_is_exit_4_and_an_unknown_version_exit_5(self):
        home = make_dir()
        self.assertEqual(run_cli(["parse"], home, stdin="hola").returncode, 4)
        v2 = self._task_text(home).replace("ris-task v1", "ris-task v2")
        self.assertEqual(run_cli(["parse"], home, stdin=v2).returncode, 5)


class ListTest(unittest.TestCase):
    def test_open_lists_sent_and_received_tasks_without_reply(self):
        home = make_dir()
        run_cli(NEW, home)
        out = run_cli(["task", "list", "--open"], home)
        self.assertRegex(out.stdout, r"sent\s+main-session \[248292\]\s+open\s+Rebase")

    def test_show_prints_every_event_of_a_task(self):
        home = make_dir()
        task_id = run_cli(NEW, home).stdout.split()[2]
        out = run_cli(["task", "show", task_id], home)
        self.assertEqual(out.returncode, 0)
        self.assertEqual(json.loads(out.stdout)[0]["event"], "sent")
        self.assertEqual(run_cli(["task", "show", "nope"], home).returncode, 6)


class ClaimTest(unittest.TestCase):
    def setUp(self):
        self.home, self.repo = make_dir(), make_dir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)

    def test_a_claim_is_kept_per_repo_and_refused_to_another_session(self):
        ok = run_cli(["claim", "fix/20", "--session", "bugs", "--note", "rebasing"], self.home, cwd=self.repo)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        taken = run_cli(["claim", "fix/20", "--session", "main-session"], self.home, cwd=self.repo)
        self.assertEqual(taken.returncode, 3)
        self.assertIn("bugs", taken.stderr)
        self.assertRegex(run_cli(["who", "fix/20"], self.home, cwd=self.repo).stdout, r"^fix/20\s+bugs\s+.*rebasing")
        other = make_dir()
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        self.assertEqual(run_cli(["who", "fix/20"], self.home, cwd=other).stdout.strip(), "fix/20 free")

    def test_only_the_owner_releases(self):
        run_cli(["claim", "a.ts", "--session", "bugs"], self.home, cwd=self.repo)
        self.assertEqual(run_cli(["release", "a.ts", "--session", "main-session"], self.home, cwd=self.repo).returncode, 3)
        self.assertEqual(run_cli(["release", "a.ts", "--session", "bugs"], self.home, cwd=self.repo).returncode, 0)
        self.assertEqual(run_cli(["who", "a.ts"], self.home, cwd=self.repo).stdout.strip(), "a.ts free")

    def test_who_with_no_resource_lists_every_claim_of_the_repo(self):
        run_cli(["claim", "a.ts", "b.ts", "--session", "bugs"], self.home, cwd=self.repo)
        lines = run_cli(["who"], self.home, cwd=self.repo).stdout.strip().splitlines()
        self.assertEqual([re.split(r"\s+", line)[0] for line in lines], ["a.ts", "b.ts"])


if __name__ == "__main__":
    unittest.main()
