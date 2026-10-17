"""The two messages sessions exchange: a task and its reply.

Both are plain text that a person can read in the receiving terminal. The first line stands alone (the recipient sees
only that line, cut to the terminal width, until it expands the message), so it leads with the sender and the goal and
ends with the id's short tail; a versioned marker block carries the fields. The block may sit anywhere in
the text: the channel wraps the message in its own lines. docs/formatos.md is the reference.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Union

VERSION = 1
STATUSES = ("done", "partial", "declined", "failed")

_OPEN = re.compile(r"^--- ris-(task|reply) v(\d+) ---$", re.M)
_MARKER = re.compile(r"^--- (end )?ris-(task|reply)( v\d+)? ---$", re.M)
_FIELD = re.compile(r"^([a-z][a-z-]*): ?(.*)$")


class FormatError(ValueError):
    """The text is not a valid task or reply (no marker, missing field, broken block)."""


class UnsupportedVersion(FormatError):
    """The marker names a version this ris does not read."""


@dataclass
class Task:
    id: str
    sender: str
    to: str
    goal: str
    done_when: str
    touches: List[str] = field(default_factory=list)
    forbidden: List[str] = field(default_factory=list)
    context: str = ""


@dataclass
class Reply:
    id: str
    sender: str
    status: str
    summary: str
    evidence: List[str] = field(default_factory=list)
    pending: List[str] = field(default_factory=list)


def _line(name: str, value: str) -> str:
    if "\n" in value or "\r" in value:
        raise FormatError(f"{name} must be a single line")
    if not value.strip():
        raise FormatError(f"{name} is empty")
    return value.strip()


def _items(name: str, values: List[str], inline: bool) -> List[str]:
    out = []
    for value in values:
        value = _line(name, value)
        if inline and ";" in value:
            raise FormatError(f"{name} item {value!r} has a ';', which separates items")
        out.append(value)
    return out


def _short(task_id: str) -> str:
    """The id's random tail: enough for a person to match a reply to its task, short enough not to push the goal past
    the preview cut."""
    return _line("id", task_id).rsplit("-", 1)[-1]


def render_task(task: Task) -> str:
    goal = _line("goal", task.goal)
    lines = [
        f"ris task from {_line('from', task.sender)}: {goal} [{_short(task.id)}]",
        f"--- ris-task v{VERSION} ---",
        f"id: {task.id}",
        f"from: {task.sender}",
        f"to: {_line('to', task.to)}",
        f"goal: {goal}",
        f"done-when: {_line('done-when', task.done_when)}",
        f"touches: {'; '.join(_items('touches', task.touches, inline=True))}",
        f"forbidden: {'; '.join(_items('forbidden', task.forbidden, inline=True))}",
        "--- context ---",
    ]
    if _MARKER.search(task.context):
        raise FormatError("context has a ris marker line, which would cut the message; quote it differently")
    if task.context.strip():
        lines.append(task.context.strip("\n"))
    lines.append("--- end ris-task ---")
    return "\n".join(lines) + "\n"


def render_reply(reply: Reply) -> str:
    if reply.status not in STATUSES:
        raise FormatError(f"status must be one of {', '.join(STATUSES)}")
    summary = _line("summary", reply.summary)
    lines = [
        f"ris reply from {_line('from', reply.sender)} ({reply.status}): {summary} [{_short(reply.id)}]",
        f"--- ris-reply v{VERSION} ---",
        f"id: {reply.id}",
        f"from: {reply.sender}",
        f"status: {reply.status}",
        f"summary: {summary}",
        "evidence:",
        *[f"- {item}" for item in _items("evidence", reply.evidence, inline=False)],
        "pending:",
        *[f"- {item}" for item in _items("pending", reply.pending, inline=False)],
        "--- end ris-reply ---",
    ]
    return "\n".join(lines) + "\n"


def parse(text: str) -> Union[Task, Reply]:
    """The first task or reply block in `text`. Raises FormatError (or UnsupportedVersion)."""
    opening = _OPEN.search(text)
    if not opening:
        raise FormatError("no ris-task or ris-reply marker in the text")
    kind, version = opening.group(1), int(opening.group(2))
    if version != VERSION:
        raise UnsupportedVersion(f"ris-{kind} v{version}: this ris reads v{VERSION}")
    end = f"--- end ris-{kind} ---"
    closing = re.compile(rf"^{re.escape(end)}$", re.M).search(text, opening.end())
    if not closing:
        raise FormatError(f"no '{end}' line: the message is cut")
    body = text[opening.end():closing.start()].strip("\n").splitlines()
    return _parse_task(body) if kind == "task" else _parse_reply(body)


def _fields(lines: List[str], kind: str) -> dict:
    out = {}
    for line in lines:
        match = _FIELD.match(line)
        if not match:
            raise FormatError(f"ris-{kind}: unexpected line {line!r}")
        out[match.group(1)] = match.group(2).strip()
    return out


def _require(fields: dict, names: List[str], kind: str) -> None:
    missing = [n for n in names if not fields.get(n)]
    if missing:
        raise FormatError(f"ris-{kind}: missing {', '.join(missing)}")


def _split(value: str) -> List[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def _parse_task(lines: List[str]) -> Task:
    if "--- context ---" not in lines:
        raise FormatError("ris-task: no '--- context ---' line")
    cut = lines.index("--- context ---")
    fields = _fields(lines[:cut], "task")
    _require(fields, ["id", "from", "to", "goal", "done-when"], "task")
    return Task(id=fields["id"], sender=fields["from"], to=fields["to"], goal=fields["goal"],
                done_when=fields["done-when"], touches=_split(fields.get("touches", "")),
                forbidden=_split(fields.get("forbidden", "")), context="\n".join(lines[cut + 1:]).strip("\n"))


def _parse_reply(lines: List[str]) -> Reply:
    fields, lists, current = {}, {"evidence": [], "pending": []}, None
    for line in lines:
        if line in ("evidence:", "pending:"):
            current = line[:-1]
        elif current and line.startswith("- "):
            lists[current].append(line[2:].strip())
        else:
            current = None
            fields.update(_fields([line], "reply"))
    _require(fields, ["id", "from", "status", "summary"], "reply")
    if fields["status"] not in STATUSES:
        raise FormatError(f"ris-reply: status {fields['status']!r} is not one of {', '.join(STATUSES)}")
    return Reply(id=fields["id"], sender=fields["from"], status=fields["status"], summary=fields["summary"],
                 evidence=lists["evidence"], pending=lists["pending"])
