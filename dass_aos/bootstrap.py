"""Bootstrap and initialization logic for DASS-AOS."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from .constants import AOS_DIR_NAME, TEMPLATES_DIR, VERSION
from .sync import sync_all_instructions
from .verifier import detect_stack_commands

# Git hook: delegates to .aos/hooks/pre_commit.py; never blocks a commit if python is missing
GIT_PRE_COMMIT = (
    "#!/bin/sh\n"
    "PY=$(command -v python3 || command -v python) || { echo '[DASS-AOS] python no encontrado, se omite verify'; exit 0; }\n"
    '"$PY" .aos/hooks/pre_commit.py\n'
)


def copy_missing(src: Path, dst: Path) -> None:
    """Copy every file under src into dst, never overwriting existing files."""
    for item in src.rglob("*"):
        if not item.is_file() or "__pycache__" in item.parts:
            continue
        target = dst / item.relative_to(src)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def init_project(
    project_root: Path,
    project_name: Optional[str] = None,
    force: bool = False,
) -> dict:
    """Initialize DASS-AOS in a target project."""
    project_root = project_root.resolve()
    project_name = project_name or project_root.name

    aos_dir = project_root / AOS_DIR_NAME

    # 1. Empty state directories the templates don't provide
    for sub in ["memory", "plans/active", "plans/archive"]:
        (aos_dir / sub).mkdir(parents=True, exist_ok=True)

    # 2. Templates (layout mirrors .aos/)
    copy_missing(TEMPLATES_DIR, aos_dir)

    # 3. Create .aos/config.json
    config_file = aos_dir / "config.json"
    if not config_file.exists() or force:
        config_data = {
            "project_name": project_name,
            "aos_version": VERSION,
            **detect_stack_commands(project_root),
            "client_generator": "generic",
        }
        config_file.write_text(json.dumps(config_data, indent=2), encoding="utf-8")

    # 4. Create .aos/mcp-config.json with resolved paths
    mcp_file = aos_dir / "mcp-config.json"
    if not mcp_file.exists() or force:
        memory_db_path = aos_dir / "memory" / f"{project_name}.db"
        mcp_data = {
            "mcpServers": {
                "codebase-memory": {
                    "command": "codebase-memory-mcp",
                    "args": [],
                    "env": {
                        "CODEBASE_MEMORY_DB": str(memory_db_path),
                    },
                },
            },
        }
        mcp_file.write_text(json.dumps(mcp_data, indent=2), encoding="utf-8")

    # 5. Sync agent instruction files in project root
    sync_results = sync_all_instructions(project_root, create_missing=True)

    # 6. Native manifests are per developer (ADR-004): keep them out of git
    gitignore = project_root / ".gitignore"
    if (project_root / ".git").exists() or gitignore.exists():
        current = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        if ".aos/native/" not in current.splitlines():
            gitignore.write_text((current.rstrip("\n") + "\n" if current else "") + ".aos/native/\n", encoding="utf-8")

    # 7. Install git pre-commit hook if a repo exists and no hook is present
    git_pre_commit = project_root / ".git" / "hooks" / "pre-commit"
    if git_pre_commit.parent.exists() and not git_pre_commit.exists():
        try:
            git_pre_commit.write_bytes(GIT_PRE_COMMIT.encode("utf-8"))
        except OSError:
            pass

    return {
        "status": "success",
        "project_name": project_name,
        "project_root": str(project_root),
        "aos_dir": str(aos_dir),
        "sync_results": sync_results,
    }
