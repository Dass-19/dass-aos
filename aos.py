#!/usr/bin/env python3
"""DASS-AOS root executable entrypoint."""
import sys
from pathlib import Path

# Add repo root to sys.path so dass_aos package is always importable
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dass_aos.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
