#!/usr/bin/env python3
"""DASS-AOS git pre-commit hook (ADR-008).

Two independent checks:
1. `deny_paths` from `.aos/config.json`: refuses to commit secrets (`.env`, keys, `.ssh/`...).
   This one runs even when DASS-AOS is not installed in the current Python.
2. `aos verify`: project linters and tests. Skipped with a message if DASS-AOS is missing,
   so the hook never blocks a commit for a tooling reason.

Bypass (deliberate, not accidental): `git commit --no-verify`.
"""
from __future__ import annotations

import fnmatch
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

CONFIG = Path(".aos") / "config.json"


def staged_files() -> list[str]:
    """Repo-relative paths staged for this commit (adds/copies/modifies/renames)."""
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def deny_paths() -> list[str]:
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    paths = data.get("deny_paths") if isinstance(data, dict) else None
    return [str(p) for p in paths] if isinstance(paths, list) else []


def matches(path: str, pattern: str) -> bool:
    """A pattern matches the file name, the repo-relative path, or any directory segment (`x/`)."""
    if pattern.endswith("/"):
        return path.startswith(pattern) or f"/{pattern}" in path
    return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(Path(path).name, pattern)


def blocked(files: list[str], patterns: list[str]) -> list[tuple[str, str]]:
    return [(f, p) for f in files for p in patterns if matches(f, p)]


def run_verify() -> int:
    if importlib.util.find_spec("dass_aos") is None:
        print("[DASS-AOS] dass-aos no esta instalado en este Python; se omite verify (pip install dass-aos).")
        return 0
    print("[DASS-AOS] Ejecutando verificacion pre-commit...")
    res = subprocess.run([sys.executable, "-m", "dass_aos", "verify"], check=False)
    if res.returncode != 0:
        print("[DASS-AOS] La verificacion fallo. Corrige los problemas antes de commitear.", file=sys.stderr)
    return res.returncode


def main() -> int:
    patterns = deny_paths()
    hits = blocked(staged_files(), patterns)
    if hits:
        print("[DASS-AOS] Commit bloqueado: hay archivos que no deben versionarse.", file=sys.stderr)
        for path, pattern in hits:
            print(f"  - {path} (coincide con '{pattern}' en deny_paths)", file=sys.stderr)
        print(
            "[DASS-AOS] Quita el archivo del stage (`git restore --staged <archivo>`), añádelo a .gitignore, "
            "o ajusta `deny_paths` en .aos/config.json.",
            file=sys.stderr,
        )
        return 1
    return run_verify()


if __name__ == "__main__":
    sys.exit(main())
