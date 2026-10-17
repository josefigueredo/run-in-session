from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TEMP = []


def make_dir() -> Path:
    tmp = tempfile.TemporaryDirectory()
    _TEMP.append(tmp)
    return Path(tmp.name)


def run_cli(args: List[str], home: Path, stdin: str = "", cwd: "Path | None" = None) -> subprocess.CompletedProcess:
    """Runs ris.py as a user would, with its state in `home` (RIS_HOME)."""
    env = dict(os.environ, RIS_HOME=str(home))
    return subprocess.run([sys.executable, str(ROOT / "ris.py"), *args], input=stdin, capture_output=True, text=True,
                          env=env, cwd=str(cwd) if cwd else None)
