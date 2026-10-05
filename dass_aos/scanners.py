"""Security scanning module for Semgrep (SAST) and Checkov (IaC)."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .constants import configure_utf8_output


def check_tool_installed(tool_name: str) -> Optional[str]:
    """Check if tool is in PATH."""
    return shutil.which(tool_name)


def run_semgrep(
    target_path: Path,
    dry_run: bool = False,
    strict: bool = False,
    config: str = "auto",
) -> int:
    """Run Semgrep SAST scan or dry-run."""
    executable = check_tool_installed("semgrep")

    if not executable:
        print("[semgrep-scan] Semgrep is not installed in current environment.")
        if dry_run or not strict:
            print(f"[semgrep-scan] DRY-RUN: would execute -> semgrep --config {config} --config p/security-audit --error \"{target_path}\"")
            print("[semgrep-scan] Install with: pip install semgrep")
            return 0
        else:
            print("[semgrep-scan] ERROR: Semgrep missing and strict mode enabled.", file=sys.stderr)
            return 2

    if dry_run:
        print(f"[semgrep-scan] DRY-RUN: semgrep --config {config} --config p/security-audit --error \"{target_path}\"")
        return 0

    cmd = [
        executable,
        "--config", config,
        "--config", "p/security-audit",
        "--error",
        str(target_path),
    ]
    print(f"[semgrep-scan] Executing on: {target_path}")
    try:
        proc = subprocess.run(cmd, check=False)
        return proc.returncode
    except Exception as exc:
        print(f"[semgrep-scan] Execution failed: {exc}", file=sys.stderr)
        return 1


def run_checkov(
    target_path: Path,
    dry_run: bool = False,
    strict: bool = False,
) -> int:
    """Run Checkov IaC scan or dry-run."""
    executable = check_tool_installed("checkov")

    if not executable:
        print("[checkov-scan] Checkov is not installed in current environment.")
        if dry_run or not strict:
            print(f"[checkov-scan] DRY-RUN: would execute -> checkov -d \"{target_path}\" --quiet --compact")
            print("[checkov-scan] Install with: pip install checkov")
            return 0
        else:
            print("[checkov-scan] ERROR: Checkov missing and strict mode enabled.", file=sys.stderr)
            return 2

    if dry_run:
        print(f"[checkov-scan] DRY-RUN: checkov -d \"{target_path}\" --quiet --compact")
        return 0

    cmd = [
        executable,
        "-d", str(target_path),
        "--quiet",
        "--compact",
    ]
    print(f"[checkov-scan] Executing on: {target_path}")
    try:
        proc = subprocess.run(cmd, check=False)
        return proc.returncode
    except Exception as exc:
        print(f"[checkov-scan] Execution failed: {exc}", file=sys.stderr)
        return 1


def run_security_scans(
    target_path: Path,
    tool: str = "all",
    dry_run: bool = False,
    strict: bool = False,
) -> int:
    """Run requested security scans and return combined status."""
    configure_utf8_output()
    target_path = target_path.resolve()
    print(f"=== DASS-AOS Security Scan on '{target_path.name}' ===")

    overall_code = 0

    if tool in ("all", "semgrep"):
        code = run_semgrep(target_path, dry_run=dry_run, strict=strict)
        if code != 0:
            overall_code = code

    if tool in ("all", "checkov"):
        code = run_checkov(target_path, dry_run=dry_run, strict=strict)
        if code != 0 and overall_code == 0:
            overall_code = code

    print(f"=== Scan Finished (Exit Code: {overall_code}) ===")
    return overall_code
