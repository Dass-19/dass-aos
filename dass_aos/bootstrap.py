"""Bootstrap and initialization logic for DASS-AOS."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from .constants import AOS_DIR_NAME, ENGINE_ROOT, VERSION
from .sync import sync_all_instructions


def init_project(
    project_root: Path,
    project_name: Optional[str] = None,
    force: bool = False,
) -> dict:
    """Initialize DASS-AOS in a target project."""
    project_root = project_root.resolve()
    project_name = project_name or project_root.name

    aos_dir = project_root / AOS_DIR_NAME
    aos_dir.mkdir(parents=True, exist_ok=True)

    # 1. Directory Structure inside .aos/
    subdirs = [
        "contracts/events",
        "contracts/http",
        "contracts/schemas",
        "knowledge/gotchas",
        "plans/active",
        "plans/archive",
        "plans/templates",
        "decisions",
        "memory",
    ]
    for sub in subdirs:
        (aos_dir / sub).mkdir(parents=True, exist_ok=True)

    # 2. Copy templates from ENGINE_ROOT if available
    # Contracts
    engine_contracts = ENGINE_ROOT / "contracts"
    if engine_contracts.exists():
        for item in (engine_contracts / "events").glob("*"):
            if item.is_file() and not (aos_dir / "contracts" / "events" / item.name).exists():
                shutil.copy2(item, aos_dir / "contracts" / "events" / item.name)
        for item in (engine_contracts / "http").glob("*"):
            if item.is_file() and not (aos_dir / "contracts" / "http" / item.name).exists():
                shutil.copy2(item, aos_dir / "contracts" / "http" / item.name)
        if (engine_contracts / "schemas").exists():
            for item in (engine_contracts / "schemas").glob("*"):
                if item.is_file() and not (aos_dir / "contracts" / "schemas" / item.name).exists():
                    shutil.copy2(item, aos_dir / "contracts" / "schemas" / item.name)

    # Knowledge
    engine_knowledge = ENGINE_ROOT / "knowledge"
    if engine_knowledge.exists():
        for k_file in engine_knowledge.glob("*.md"):
            dest = aos_dir / "knowledge" / k_file.name
            if not dest.exists():
                shutil.copy2(k_file, dest)

    # Gotchas readme
    gotchas_readme = aos_dir / "knowledge" / "gotchas" / "README.md"
    if not gotchas_readme.exists():
        gotchas_readme.write_text(
            "# Trampas Arquitectónicas y Gotchas\n\n"
            "Documenta aquí las trampas y bugs no obvios para que los agentes eviten repetirlos.\n"
            "Formato: `<nombre>.md` con frontmatter `title:` y descripción clara.\n",
            encoding="utf-8",
        )

    # Plans templates
    engine_plans = ENGINE_ROOT / "plans" / "templates"
    if engine_plans.exists():
        for p_file in engine_plans.glob("*.md"):
            dest = aos_dir / "plans" / "templates" / p_file.name
            if not dest.exists():
                shutil.copy2(p_file, dest)

    # Decisions (ADRs): Solo copiar la plantilla para el proyecto, nunca los ADRs internos del framework
    engine_decisions = ENGINE_ROOT / "decisions"
    if engine_decisions.exists():
        plantilla = engine_decisions / "ADR-001-plantilla.md"
        if plantilla.exists():
            dest = aos_dir / "decisions" / "ADR-001-plantilla.md"
            if not dest.exists():
                shutil.copy2(plantilla, dest)

    # 3. Create .aos/config.json
    config_file = aos_dir / "config.json"
    if not config_file.exists() or force:
        config_data = {
            "project_name": project_name,
            "aos_version": VERSION,
            "lint_command": None,
            "test_command": None,
            "migration_command": None,
            "client_generator": "generic",
        }
        config_file.write_text(json.dumps(config_data, indent=2), encoding="utf-8")

    # 4. Create .aos/mcp-config.json with resolved paths
    mcp_file = aos_dir / "mcp-config.json"
    if not mcp_file.exists() or force:
        memory_db_path = aos_dir / "memory" / f"{project_name}.db"
        mcp_data = {
            "mcpServers": {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", str(project_root)],
                },
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

    # 6. Copy pre-commit hook template
    hooks_dir = aos_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    pre_commit_py = hooks_dir / "pre_commit.py"
    if not pre_commit_py.exists():
        pre_commit_py.write_text(
            '"""Hook de pre-commit para DASS-AOS."""\n'
            "import sys\n\n"
            "print('Ejecutando comprobaciones pre-commit de DASS-AOS...')\n"
            "# Ejecutar la lógica de verificación aquí\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )

    # If git repo exists, optionally install git pre-commit hook
    git_hooks_dir = project_root / ".git" / "hooks"
    if git_hooks_dir.exists():
        git_pre_commit = git_hooks_dir / "pre-commit"
        if not git_pre_commit.exists():
            try:
                git_pre_commit.write_text(
                    "#!/bin/sh\n"
                    "python aos.py verify || exit 1\n",
                    encoding="utf-8",
                )
            except Exception:
                pass

    return {
        "status": "success",
        "project_name": project_name,
        "project_root": str(project_root),
        "aos_dir": str(aos_dir),
        "sync_results": sync_results,
    }
