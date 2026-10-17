"""What sessions remember: each session's log of the tasks it sent and received, and claims on branches or files.

Everything lives under one folder per user, outside every repo ($RIS_HOME, default ~/.run-in-session). Two sessions of
the same user share that folder, so each log is kept apart under sessions/<ref>/, where <ref> is the session's own
[ref] from ListAgents (it survives a /rename). Claims are shared on purpose: they say which session holds what.
Peers in other machines see none of it: the messages carry everything the other side needs.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional


def home() -> Path:
    path = Path(os.environ.get("RIS_HOME") or Path.home() / ".run-in-session")
    path.mkdir(parents=True, exist_ok=True)
    return path


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


# --- log (one per session) --------------------------------------------------------------------------------------------

# Every [ref] ListAgents showed on 2026-10-17 (19 of them) was 6 lowercase hex digits. Lowercase hex of 4 to 32 keeps a
# session name (bugs, main-session, emu) out, which would otherwise open a second log silently; a name made only of
# a-f and digits would still pass.
REF = re.compile(r"^[0-9a-f]{4,32}$")


def _log(ref: str) -> Path:
    if not REF.match(ref):
        raise ValueError(f"session ref {ref!r}: use the [ref] ListAgents shows for this session, like 48ff1d")
    path = home() / "sessions" / ref
    path.mkdir(parents=True, exist_ok=True)
    return path / "log.jsonl"


def append(ref: str, event: dict) -> None:
    with _log(ref).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": now(), **event}, ensure_ascii=False) + "\n")


def events(ref: str, task_id: Optional[str] = None) -> List[dict]:
    path = _log(ref)
    if not path.exists():
        return []
    out = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [e for e in out if task_id is None or e["id"] == task_id]


def tasks(ref: str) -> List[dict]:
    """One row per task of this session, in the order first seen: who, which way, and whether a reply closed it."""
    rows: Dict[str, dict] = {}
    for e in events(ref):
        if e["event"] in ("sent", "received"):
            rows.setdefault(e["id"], {"id": e["id"], "way": e["event"], "peer": e["peer"], "peer_ref": e.get("peer_ref", ""),
                                      "goal": e.get("goal", ""), "status": "open",
                                      "when": e.get("when", "now")})
        elif e["event"] in ("replied", "reply-received") and e["id"] in rows:
            rows[e["id"]]["status"] = e["status"]
    return list(rows.values())


# --- claims ------------------------------------------------------------------------------------------------------------

def repo_key(cwd: Optional[str] = None) -> str:
    """The repo the claims belong to: its shared git dir, so every worktree of a clone sees the same claims."""
    out = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=cwd or str(Path.cwd()),
                         capture_output=True, text=True)
    return str(Path(out.stdout.strip()).resolve()) if out.returncode == 0 else "(no repo)"


def _claims_file() -> Path:
    return home() / "claims.json"


def claims() -> Dict[str, Dict[str, dict]]:
    path = _claims_file()
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_claims(data: Dict[str, Dict[str, dict]]) -> None:
    tmp = _claims_file().with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(_claims_file())


@contextlib.contextmanager
def claims_lock():
    """Held while a claim or release reads and writes claims.json, so two sessions at once do not lose one."""
    with (home() / "claims.lock").open("a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
