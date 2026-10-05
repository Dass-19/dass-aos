"""Verification engine for linting, testing, and database migrations."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

from .constants import AOS_DIR_NAME, configure_utf8_output


def load_project_config(project_root: Path) -> Dict[str, Optional[str]]:
    """Load configuration from .aos/config.json if present."""
    config_file = project_root / AOS_DIR_NAME / "config.json"
    if config_file.exists():
        try:
            return json.loads(config_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def detect_stack_commands(project_root: Path) -> Dict[str, Optional[str]]:
    """Infer common lint/test commands based on project indicators."""
    inferred = {
        "lint_command": None,
        "test_command": None,
        "migration_command": None,
    }

    # Node.js
    pkg_json = project_root / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            scripts = data.get("scripts", {})
            if "lint" in scripts:
                inferred["lint_command"] = "npm run lint"
            if "test" in scripts:
                inferred["test_command"] = "npm test"
        except Exception:
            pass

    # Python
    if not inferred["test_command"]:
        if (project_root / "pyproject.toml").exists() or (project_root / "setup.py").exists() or (project_root / "tests").exists():
            inferred["test_command"] = "python -m unittest"
            inferred["lint_command"] = "ruff check ."

    # Rust
    if (project_root / "Cargo.toml").exists():
        inferred["lint_command"] = "cargo clippy"
        inferred["test_command"] = "cargo test"

    # Go
    if (project_root / "go.mod").exists():
        inferred["test_command"] = "go test ./..."

    return inferred


def run_verification(
    project_root: Path,
    check_type: str = "all",
    strict: bool = False,
) -> int:
    """Run verification checks and report status."""
    configure_utf8_output()
    project_root = project_root.resolve()
    config = load_project_config(project_root)
    inferred = detect_stack_commands(project_root)

    print(f"=== DASS-AOS Verification on '{project_root.name}' ===")

    overall_code = 0
    checks = ["lint", "test", "migration"] if check_type == "all" else [check_type]

    for check in checks:
        key = f"{check}_command"
        cmd = config.get(key) or inferred.get(key)

        if not cmd:
            print(f"[{check.upper()}] SKIPPED: No {key} configured in .aos/config.json")
            if strict:
                overall_code = 1
            continue

        print(f"[{check.upper()}] Executing: {cmd}")
        try:
            proc = subprocess.run(cmd, shell=True, cwd=str(project_root), check=False)
            if proc.returncode != 0:
                print(f"[{check.upper()}] FAILED (exit code: {proc.returncode})", file=sys.stderr)
                overall_code = proc.returncode
            else:
                print(f"[{check.upper()}] PASSED")
        except Exception as exc:
            print(f"[{check.upper()}] Execution error: {exc}", file=sys.stderr)
            overall_code = 1

    print(f"=== Verification Finished (Exit Code: {overall_code}) ===")
    return overall_code
