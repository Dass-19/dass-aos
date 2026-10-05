#!/usr/bin/env python3
"""DASS-AOS git pre-commit hook."""
import sys
import subprocess

def main() -> int:
    print("[DASS-AOS] Running pre-commit verification...")
    # Try running python aos.py verify
    res = subprocess.run([sys.executable, "aos.py", "verify"], check=False)
    if res.returncode != 0:
        print("[DASS-AOS] Pre-commit checks failed! Please resolve issues before committing.", file=sys.stderr)
        return res.returncode
    return 0

if __name__ == "__main__":
    sys.exit(main())
