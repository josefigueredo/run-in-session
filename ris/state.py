"""What this session remembers: a log of the tasks it sent and received, and claims on branches or files.

Both live under one folder per user, outside every repo ($RIS_HOME, default ~/.run-in-session): peers can sit in other
repos or on other machines, so nothing is shared through it. The messages carry everything the other side needs.
"""
from __future__ import annotations

import json
import os
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


# --- log ---------------------------------------------------------------------------------------------------------------

def append(event: dict) -> None:
    with (home() / "log.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": now(), **event}, ensure_ascii=False) + "\n")


def events(task_id: Optional[str] = None) -> List[dict]:
    path = home() / "log.jsonl"
    if not path.exists():
        return []
    out = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [e for e in out if task_id is None or e["id"] == task_id]


def tasks() -> List[dict]:
    """One row per task, in the order first seen: who, which way, and whether a reply closed it."""
    rows: Dict[str, dict] = {}
    for e in events():
        if e["event"] in ("sent", "received"):
            rows.setdefault(e["id"], {"id": e["id"], "way": e["event"], "peer": e["peer"], "peer_ref": e.get("peer_ref", ""),
                                      "goal": e.get("goal", ""), "status": "open"})
        elif e["event"] in ("replied", "reply-received") and e["id"] in rows:
            rows[e["id"]]["status"] = e["status"]
    return list(rows.values())


# --- claims ------------------------------------------------------------------------------------------------------------

def repo_key(cwd: Optional[Path] = None) -> str:
    """The repo the claims belong to: its shared git dir, so every worktree of a clone sees the same claims."""
    out = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=str(cwd or Path.cwd()),
                         capture_output=True, text=True)
    return str(Path(out.stdout.strip()).resolve()) if out.returncode == 0 else "(no repo)"


def _claims_file() -> Path:
    return home() / "claims.json"


def claims() -> Dict[str, Dict[str, dict]]:
    path = _claims_file()
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_claims(data: Dict[str, Dict[str, dict]]) -> None:
    tmp = _claims_file().with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(_claims_file())
