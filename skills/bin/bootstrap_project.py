#!/usr/bin/env python3
"""Shim for bootstrap_project delegating to dass_aos.bootstrap."""
import sys
from pathlib import Path

# Ensure root is in sys.path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse  # noqa: E402
from dass_aos.bootstrap import init_project  # noqa: E402

def main():
    parser = argparse.ArgumentParser(description="Bootstrap DASS-AOS into target project")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    res = init_project(Path(args.project_root), project_name=args.project_name, force=args.force)
    print(f"Initialized DASS-AOS in {res['project_root']}")

if __name__ == "__main__":
    main()
