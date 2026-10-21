"""Verification engine for linting, testing, and database migrations."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

from .constants import AOS_DIR_NAME, configure_utf8_output
from .ui import (
    Card,
    badge_fail,
    badge_pass,
    badge_skip,
    bold,
    cyan,
    dim,
    green,
    red,
)


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
        inferred["lint_command"] = "go vet ./..."
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

    card = Card("Verificación", project_root.name)
    card.field("Ruta", dim(str(project_root)))
    card.field("Alcance", bold(check_type))
    card.empty()
    card.line(bold("Comprobaciones del proyecto:"))

    overall_code = 0
    checks = ["lint", "test", "migration"] if check_type == "all" else [check_type]

    for check in checks:
        key = f"{check}_command"
        cmd = config.get(key) or inferred.get(key)

        if not cmd:
            card.line(f"  {badge_skip('SKIPPED')}  {bold(check.upper()):<10} {dim('sin comando configurado')}")
            if strict:
                overall_code = 1
            continue

        exe = cmd.split()[0]
        if shutil.which(exe) is None:
            card.line(f"  {badge_skip('SKIPPED')}  {bold(check.upper()):<10} {dim(f'herramienta no instalada ({exe})')}")
            if strict:
                overall_code = 1
            continue

        print(f"\n{bold(cyan('▶'))} {bold(f'[{check.upper()}]')} {dim(cmd)}")
        try:
            proc = subprocess.run(cmd, shell=True, cwd=str(project_root), check=False)
            if proc.returncode != 0:
                card.line(f"  {badge_fail('FAILED')}   {bold(check.upper()):<10} {red(f'código {proc.returncode}')} — {dim(cmd)}")
                overall_code = proc.returncode
            else:
                card.line(f"  {badge_pass('PASSED')}   {bold(check.upper()):<10} {green('exitoso')} — {dim(cmd)}")
        except Exception as exc:
            card.line(f"  {badge_fail('ERROR')}    {bold(check.upper()):<10} {exc}")
            overall_code = 1

    card.empty()
    if overall_code == 0:
        card.field("Resultado", green(bold("✓ Todas las comprobaciones pasaron")))
    else:
        card.field("Resultado", red(bold(f"✖ Fallaron comprobaciones (código {overall_code})")))

    print("\n" + card.render())
    return overall_code
