#!/usr/bin/env python3
"""Shim for memory_refresh delegating to dass_aos.memory."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse  # noqa: E402
from dass_aos.memory import run_memory_refresh  # noqa: E402

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--gotchas-limit", type=int, default=5)
    args = parser.parse_args()

    run_memory_refresh(Path(args.project_root), gotchas_limit=args.gotchas_limit)

if __name__ == "__main__":
    main()
