"""ris as the agent runs it: render, parse, log and claims, with their exit codes."""
from __future__ import annotations

import json
import re
import subprocess
import unittest

from helpers import make_dir, run_cli

ME, PEER = "48ff1d", "248292"
NEW = ["task", "new", "--as", ME, "--from", "bugs", "--to", "main-session", "--to-ref", PEER,
       "--goal", "Rebase feat/mcp-integration on fix/20", "--done", "merges clean and tests pass",
       "--touch", "feat/mcp-integration", "--forbid", "push"]


def log(home, ref: str = ME) -> list:
    path = home / "sessions" / ref / "log.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def task_id_of(text: str) -> str:
    return re.search(r"^id: (\S+)$", text, re.M).group(1)


def reply_text(home, task_id: str, ref: str = PEER) -> str:
    return run_cli(["task", "reply", task_id, "--as", ref, "--from", "main-session", "--status", "done",
                    "--summary", "Rebased", "--evidence", "git log -1: abc"], home).stdout


class TaskNewTest(unittest.TestCase):
    def test_it_prints_the_message_and_logs_it_as_sent_with_the_peer_ref(self):
        home = make_dir()
        out = run_cli(NEW + ["--context", "fix/20 is pushed"], home)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertRegex(out.stdout.splitlines()[0], r"^ris task from bugs: Rebase.* \[[0-9a-f]{4}\]$")
        self.assertIn("fix/20 is pushed", out.stdout)
        [entry] = log(home)
        self.assertEqual((entry["event"], entry["peer"], entry["peer_ref"]), ("sent", "main-session", PEER))
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
        out = run_cli(["task", "new", "--as", ME, "--from", "a", "--to", "b", "--goal", "x\ny", "--done", "d"], make_dir())
        self.assertEqual(out.returncode, 2)

    def test_a_context_line_that_would_close_the_block_is_a_usage_error(self):
        out = run_cli(NEW + ["--context", "-"], make_dir(), stdin="forwarded:\n--- end ris-task ---\nmore\n")
        self.assertEqual(out.returncode, 2)
        self.assertIn("marker", out.stderr)

    def test_the_session_ref_is_required_and_checked(self):
        self.assertEqual(run_cli(NEW[:2] + NEW[4:], make_dir()).returncode, 2)
        bad = list(NEW)
        bad[bad.index("--as") + 1] = "../x"
        self.assertEqual(run_cli(bad, make_dir()).returncode, 2)

    def test_a_session_name_instead_of_its_ref_is_refused_without_opening_a_log(self):
        # measured 2026-10-17: before this check, `--as bugs` exited 0 and silently opened sessions/bugs/
        for name in ("bugs", "main-session", "emu", "prueba-ris", "48FF1D"):
            home = make_dir()
            out = run_cli(["task", "list", "--as", name], home)
            self.assertEqual(out.returncode, 2, name)
            self.assertIn("name", out.stderr)
            self.assertFalse((home / "sessions").exists(), name)
        self.assertEqual(run_cli(["task", "list", "--as", "e083c1"], make_dir()).returncode, 0)


class ParseTest(unittest.TestCase):
    def test_a_received_task_prints_json_and_is_logged_from_its_sender(self):
        home = make_dir()
        text = "Another Claude session sent a message:\n" + run_cli(NEW, home).stdout
        out = run_cli(["parse", "--as", PEER], home, stdin=text)
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual((data["kind"], data["from"], data["goal"]), ("task", "bugs", "Rebase feat/mcp-integration on fix/20"))
        [entry] = log(home, PEER)
        self.assertEqual((entry["event"], entry["peer"]), ("received", "bugs"))

    def test_two_sessions_sharing_one_home_keep_separate_logs(self):
        home = make_dir()  # the normal case: same user, same machine, same ~/.run-in-session
        task = run_cli(NEW, home).stdout
        task_id = task_id_of(task)
        self.assertEqual(run_cli(["parse", "--as", PEER], home, stdin=task).returncode, 0)
        reply = reply_text(home, task_id)
        self.assertRegex(run_cli(["task", "list", "--open", "--as", ME], home).stdout, r"sent\s+main-session \[248292\]\s+open")
        self.assertRegex(run_cli(["task", "list", "--as", PEER], home).stdout, r"received\s+bugs\s+done")
        out = run_cli(["parse", "--as", ME], home, stdin=reply)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(run_cli(["task", "list", "--open", "--as", ME], home).stdout.strip(), "no open tasks")

    def test_a_reply_to_a_task_another_local_session_sent_is_flagged(self):
        home = make_dir()
        task_id = task_id_of(run_cli(NEW, home).stdout)  # sent by ME
        out = run_cli(["parse", "--as", "c0ffee"], home, stdin=reply_text(home, task_id))
        self.assertEqual(out.returncode, 6)
        self.assertIn("not in this session's log", out.stderr)
        self.assertEqual(json.loads(out.stdout)["id"], task_id)

    def test_text_with_no_message_is_exit_4_and_an_unknown_version_exit_5(self):
        home = make_dir()
        self.assertEqual(run_cli(["parse", "--as", ME], home, stdin="hola").returncode, 4)
        v2 = run_cli(NEW, home).stdout.replace("ris-task v1", "ris-task v2")
        self.assertEqual(run_cli(["parse", "--as", ME], home, stdin=v2).returncode, 5)


class ListTest(unittest.TestCase):
    def test_open_lists_sent_tasks_without_reply(self):
        home = make_dir()
        run_cli(NEW, home)
        out = run_cli(["task", "list", "--open", "--as", ME], home)
        self.assertRegex(out.stdout, r"sent\s+main-session \[248292\]\s+open\s+Rebase")

    def test_show_prints_every_event_of_a_task(self):
        home = make_dir()
        task_id = task_id_of(run_cli(NEW, home).stdout)
        out = run_cli(["task", "show", task_id, "--as", ME], home)
        self.assertEqual(out.returncode, 0)
        self.assertEqual(json.loads(out.stdout)[0]["event"], "sent")
        self.assertEqual(run_cli(["task", "show", "nope", "--as", ME], home).returncode, 6)


class InboxTest(unittest.TestCase):
    def test_inbox_lists_received_tasks_without_a_reply_and_says_when(self):
        home = make_dir()
        later = run_cli(NEW + ["--when", "after-current"], home).stdout
        now = run_cli(NEW, home).stdout
        self.assertIn("when: after-current", later)
        for text in (later, now):
            run_cli(["parse", "--as", PEER], home, stdin=text)
        run_cli(["task", "reply", task_id_of(now), "--as", PEER, "--from", "main-session", "--status", "done",
                 "--summary", "ok"], home)
        out = run_cli(["task", "list", "--inbox", "--as", PEER], home)
        self.assertEqual(out.returncode, 0, out.stderr)
        [row] = out.stdout.strip().splitlines()
        self.assertIn(task_id_of(later), row)
        self.assertIn("after-current", row)
        self.assertEqual(run_cli(["task", "list", "--inbox", "--as", ME], home).stdout.strip(), "no tasks waiting here")

    def test_marks_print_the_terminal_markers_and_the_send_summary(self):
        home = make_dir()
        text = run_cli(NEW, home).stdout
        task_id = task_id_of(text)
        run_cli(["parse", "--as", PEER], home, stdin=text)
        out = run_cli(["task", "marks", task_id, "--as", PEER], home)
        self.assertEqual(out.returncode, 0, out.stderr)
        short = task_id.rsplit("-", 1)[-1]
        self.assertEqual(out.stdout.splitlines(), [f"── ris {short} · tarea de bugs ──",
                                                   f"── fin ris {short} · vuelvo a lo tuyo ──",
                                                   f"ris reply {short} → bugs"])


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

    def test_dash_c_points_at_the_repo_whatever_the_cwd(self):
        run_cli(["-C", str(self.repo), "claim", "a.ts", "--session", "bugs"], self.home, cwd=make_dir())
        self.assertRegex(run_cli(["who", "a.ts"], self.home, cwd=self.repo).stdout, r"^a.ts\s+bugs")

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
