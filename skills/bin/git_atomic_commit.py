#!/usr/bin/env python3
"""Cross-platform script for true atomic commits with specified files."""
import argparse
import subprocess
import sys
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser(description="Perform a verified atomic git commit")
    parser.add_argument("--message", "-m", required=True, help="Conventional commit message")
    parser.add_argument("--files", "-f", nargs="+", required=True, help="Specific files to commit")
    args = parser.parse_args()

    # Stage only specific files
    for file_path in args.files:
        p = Path(file_path)
        if not p.exists():
            print(f"[atomic-commit] ERROR: File not found: {file_path}", file=sys.stderr)
            return 1
        res = subprocess.run(["git", "add", str(p)], check=False)
        if res.returncode != 0:
            print(f"[atomic-commit] Failed staging: {file_path}", file=sys.stderr)
            return res.returncode

    # Commit staged files
    commit_res = subprocess.run(["git", "commit", "-m", args.message], check=False)
    if commit_res.returncode == 0:
        print(f"[atomic-commit] Committed: {args.message}")
    return commit_res.returncode

if __name__ == "__main__":
    sys.exit(main())
