#!/usr/bin/env python3
"""Shim for sync_agent_instructions delegating to dass_aos.sync."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse  # noqa: E402
from dass_aos.sync import sync_all_instructions  # noqa: E402

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--create-missing", action="store_true", default=True)
    args = parser.parse_args()

    results = sync_all_instructions(Path(args.project_root), create_missing=args.create_missing)
    print(f"Synchronized instructions in {args.project_root}: {results}")

if __name__ == "__main__":
    main()
