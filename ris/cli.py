"""ris: render and read the messages sessions exchange, and keep this session's log and claims.

It never sends anything: the agent sends the printed text with its SendMessage tool. Exit codes: 0 ok, 2 usage,
3 refused (a --deny pattern matched, or the claim belongs to another session), 4 not a valid message, 5 unsupported
version, 6 unknown task id.
"""
from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
import time
from dataclasses import asdict
from typing import List, Optional

from . import formats, state
from .formats import FormatError, Reply, Task, UnsupportedVersion

OK, USAGE, REFUSED, INVALID, VERSION, UNKNOWN = 0, 2, 3, 4, 5, 6


def _err(message: str, code: int) -> int:
    print(f"ris: {message}", file=sys.stderr)
    return code


def new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


def cmd_task_new(a: argparse.Namespace) -> int:
    context = sys.stdin.read() if a.context == "-" else (a.context or "")
    task = Task(id=new_id(), sender=a.sender, to=a.to, goal=a.goal, done_when=a.done, touches=a.touch or [],
                forbidden=a.forbid or [], context=context, when=a.when)
    try:
        text = formats.render_task(task)
    except FormatError as exc:
        return _err(str(exc), USAGE)
    for pattern in a.deny or []:
        if re.search(pattern, text, re.I):
            return _err(f"the message matches --deny {pattern}; nothing was logged", REFUSED)
    state.append(a.ref, {"event": "sent", "id": task.id, "peer": task.to, "peer_ref": a.to_ref or "", "goal": task.goal})
    sys.stdout.write(text)
    return OK


def cmd_task_reply(a: argparse.Namespace) -> int:
    reply = Reply(id=a.id, sender=a.sender, status=a.status, summary=a.summary, evidence=a.evidence or [],
                  pending=a.pending or [])
    try:
        text = formats.render_reply(reply)
    except FormatError as exc:
        return _err(str(exc), USAGE)
    known = [e for e in state.events(a.ref, a.id) if e["event"] == "received"]
    state.append(a.ref, {"event": "replied", "id": a.id, "peer": known[0]["peer"] if known else "", "status": a.status})
    sys.stdout.write(text)
    return OK


def cmd_parse(a: argparse.Namespace) -> int:
    try:
        message = formats.parse(sys.stdin.read())
    except UnsupportedVersion as exc:
        return _err(str(exc), VERSION)
    except FormatError as exc:
        return _err(str(exc), INVALID)
    data = asdict(message)
    data["from"] = data.pop("sender")
    if isinstance(message, Task):
        data["kind"] = "task"
        state.append(a.ref, {"event": "received", "id": message.id, "peer": message.sender, "goal": message.goal,
                             "when": message.when})
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return OK
    data["kind"] = "reply"
    print(json.dumps(data, ensure_ascii=False, indent=1))
    if not any(e["event"] == "sent" for e in state.events(a.ref, message.id)):
        return _err(f"reply to {message.id}, which is not in this session's log: this session never sent that task",
                    UNKNOWN)
    state.append(a.ref, {"event": "reply-received", "id": message.id, "peer": message.sender, "status": message.status})
    return OK


def cmd_task_list(a: argparse.Namespace) -> int:
    rows = [r for r in state.tasks(a.ref) if not (a.open or a.inbox) or r["status"] == "open"]
    if a.inbox:
        rows = [r for r in rows if r["way"] == "received"]
    if not rows:
        print("no tasks waiting here" if a.inbox else "no open tasks" if a.open else "no tasks")
        return OK
    for r in rows:
        peer = r["peer"] + (f" [{r['peer_ref']}]" if r["peer_ref"] else "")
        when = f"  {r['when']}" if a.inbox else ""
        print(f"{r['id']}  {r['way']:<8}  {peer:<28}  {r['status']:<8}{when}  {r['goal']}")
    return OK


def cmd_task_marks(a: argparse.Namespace) -> int:
    """The lines that frame, in this terminal, the work done for a peer's task, and the summary of the reply's send."""
    received = [e for e in state.events(a.ref, a.id) if e["event"] == "received"]
    if not received:
        return _err(f"{a.id} is not a task this session received", UNKNOWN)
    short, peer = a.id.rsplit("-", 1)[-1], received[0]["peer"]
    print(f"── ris {short} · tarea de {peer} ──")
    print(f"── fin ris {short} · vuelvo a lo tuyo ──")
    print(f"ris reply {short} → {peer}")
    return OK


def cmd_task_show(a: argparse.Namespace) -> int:
    found = state.events(a.ref, a.id)
    if not found:
        return _err(f"{a.id} is not in this session's log", UNKNOWN)
    print(json.dumps(found, ensure_ascii=False, indent=1))
    return OK


def cmd_claim(a: argparse.Namespace) -> int:
    with state.claims_lock():
        return _claim(a)


def _claim(a: argparse.Namespace) -> int:
    data = state.claims()
    repo = data.setdefault(state.repo_key(a.dir), {})
    taken = [r for r in a.resources if r in repo and repo[r]["session"] != a.session]
    if taken:
        owners = ", ".join(f"{r} ({repo[r]['session']})" for r in taken)
        return _err(f"already claimed by another session: {owners}", REFUSED)
    for r in a.resources:
        repo[r] = {"session": a.session, "since": state.now(), "note": a.note or ""}
    state.save_claims(data)
    return OK


def cmd_release(a: argparse.Namespace) -> int:
    with state.claims_lock():
        return _release(a)


def _release(a: argparse.Namespace) -> int:
    data = state.claims()
    repo = data.get(state.repo_key(a.dir), {})
    foreign = [r for r in a.resources if r in repo and repo[r]["session"] != a.session]
    if foreign:
        return _err(f"not yours to release: {', '.join(foreign)}", REFUSED)
    for r in a.resources:
        repo.pop(r, None)
    state.save_claims(data)
    return OK


def cmd_who(a: argparse.Namespace) -> int:
    repo = state.claims().get(state.repo_key(a.dir), {})
    for r in a.resources or sorted(repo):
        c = repo.get(r)
        print(f"{r}  {c['session']}  {c['since']}  {c['note']}".rstrip() if c else f"{r} free")
    return OK


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ris", description=__doc__.splitlines()[0])
    p.add_argument("-C", dest="dir", help="the repo claims refer to (default: the current directory)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def me(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--as", dest="ref", required=True,
                        help="this session's own [ref] from the ListAgents header; it keeps this session's log apart")

    task = sub.add_parser("task", help="render a task or a reply, list and show the log").add_subparsers(dest="sub", required=True)
    new = task.add_parser("new", help="render a task to send and log it as sent")
    me(new)
    new.add_argument("--from", dest="sender", required=True, help="this session's name, as ListAgents shows it")
    new.add_argument("--to", required=True, help="the peer's name")
    new.add_argument("--to-ref", help="the peer's [ref] from ListAgents; it survives a /rename")
    new.add_argument("--goal", required=True)
    new.add_argument("--done", required=True, help="when the task counts as done")
    new.add_argument("--touch", action="append", help="branch or file the task may change (repeatable)")
    new.add_argument("--forbid", action="append", help="what the peer must not do (repeatable)")
    new.add_argument("--context", help="free text; '-' reads it from stdin")
    new.add_argument("--deny", action="append", help="regex: refuse if the message matches (repeatable)")
    new.add_argument("--when", choices=formats.WHENS, default="now",
                     help="after-current: the peer finishes its current work before taking this task")
    new.set_defaults(func=cmd_task_new)

    reply = task.add_parser("reply", help="render the reply to a received task and log it")
    reply.add_argument("id")
    me(reply)
    reply.add_argument("--from", dest="sender", required=True)
    reply.add_argument("--status", required=True, choices=formats.STATUSES)
    reply.add_argument("--summary", required=True)
    reply.add_argument("--evidence", action="append", help="a commit, a command and its result... (repeatable)")
    reply.add_argument("--pending", action="append", help="what is left, and for whom (repeatable)")
    reply.set_defaults(func=cmd_task_reply)

    lst = task.add_parser("list", help="the tasks in this log")
    lst.add_argument("--open", action="store_true", help="only those without a reply")
    lst.add_argument("--inbox", action="store_true", help="only tasks this session received and has not answered")
    me(lst)
    lst.set_defaults(func=cmd_task_list)

    show = task.add_parser("show", help="every event of one task")
    show.add_argument("id")
    me(show)
    show.set_defaults(func=cmd_task_show)

    marks = task.add_parser("marks", help="the terminal markers and the send summary for a received task")
    marks.add_argument("id")
    me(marks)
    marks.set_defaults(func=cmd_task_marks)

    prs = sub.add_parser("parse", help="read a received message on stdin, print it as JSON and log it")
    me(prs)
    prs.set_defaults(func=cmd_parse)

    claim = sub.add_parser("claim", help="claim branches or files of the current repo for a session")
    claim.add_argument("resources", nargs="+")
    claim.add_argument("--session", required=True)
    claim.add_argument("--note")
    claim.set_defaults(func=cmd_claim)

    release = sub.add_parser("release", help="drop this session's claims")
    release.add_argument("resources", nargs="+")
    release.add_argument("--session", required=True)
    release.set_defaults(func=cmd_release)

    who = sub.add_parser("who", help="who holds each resource of the current repo")
    who.add_argument("resources", nargs="*")
    who.set_defaults(func=cmd_who)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = parser().parse_args(argv)
    if getattr(args, "ref", None) is not None and not state.REF.match(args.ref):
        return _err(f"--as {args.ref!r}: that looks like a session name; use the [ref] ListAgents shows for this "
                    f"session, like 48ff1d (lowercase hex)", USAGE)
    return args.func(args)
