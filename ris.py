#!/usr/bin/env python3
"""Entry point: python3 ris.py <task|parse|claim|release|who> ... (see ris/cli.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ris.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
