"""Bootstrap and initialization logic for DASS-AOS."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import List, Optional

from .constants import AOS_DIR_NAME, TEMPLATES_DIR, TOOL_FILES, VERSION
from .sync import detect_tools, read_config, sync_all_instructions
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


def resolve_tools(project_root: Path, requested: Optional[List[str]]) -> List[str]:
    """Requested tools plus those already configured; with none of either, what the repo already uses.

    Validates .aos/config.json strictly here, before init writes anything.
    """
    configured = read_config(project_root).get("tools", [])
    if not isinstance(configured, list):
        raise ValueError('.aos/config.json: "tools" debe ser una lista, p. ej. ["antigravity"]')
    for source, names in (("argumento", requested or []), (".aos/config.json", configured)):
        unknown = [t for t in names if t not in TOOL_FILES]
        if unknown:
            raise ValueError(f"herramienta desconocida en {source}: {', '.join(map(str, unknown))}. Disponibles: {', '.join(TOOL_FILES)}")
    tools = list(dict.fromkeys([*configured, *(requested or [])]))
    tools = tools or detect_tools(project_root)
    if not tools:
        raise ValueError(
            "no se detectó ninguna herramienta de IA en el repo. Indica cuál usas: "
            f"aos init <herramienta> [...]. Disponibles: {', '.join(TOOL_FILES)}"
        )
    return tools


def init_project(
    project_root: Path,
    project_name: Optional[str] = None,
    force: bool = False,
    tools: Optional[List[str]] = None,
    native: bool = False,
) -> dict:
    """Initialize DASS-AOS for the given AI tools (or the ones the repo already uses).

    With `native`, also generates subagents and skills for tools with a generator (hooks stay pending: --yes).
    """
    project_root = project_root.resolve()
    project_name = project_name or project_root.name
    tools = resolve_tools(project_root, tools)  # before writing anything: our own files would look like signs

    aos_dir = project_root / AOS_DIR_NAME

    # 1. Empty state directories the templates don't provide
    for sub in ["plans/active", "plans/archive"]:
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
    config_data = read_config(project_root)
    if config_data.get("tools") != tools:
        config_data["tools"] = tools
        config_file.write_text(json.dumps(config_data, indent=2), encoding="utf-8")

    # 4. Create .aos/mcp-config.json (neutral; tools reuse the user's servers, ADR-005)
    mcp_file = aos_dir / "mcp-config.json"
    if not mcp_file.exists() or force:
        mcp_data = {
            "mcpServers": {
                # Indexes each project in the user's own DB: no per-project path (it was absolute, not portable)
                "codebase-memory": {"command": "codebase-memory-mcp", "args": []},
                # Remote server, no Node needed; API key optional (more rate limit)
                "context7": {"url": "https://mcp.context7.com/mcp"},
            },
        }
        mcp_file.write_text(json.dumps(mcp_data, indent=2), encoding="utf-8")

    # 5. Sync agent instruction files in project root (also ensures the .gitignore entries)
    sync_results = sync_all_instructions(project_root)

    # 6. Install git pre-commit hook if a repo exists and no hook is present
    git_pre_commit = project_root / ".git" / "hooks" / "pre-commit"
    if git_pre_commit.parent.exists() and not git_pre_commit.exists():
        try:
            git_pre_commit.write_bytes(GIT_PRE_COMMIT.encode("utf-8"))
        except OSError:
            pass

    # 7. Native files last: a broken project role must not leave the rest of init undone
    native_results = {}
    if native:
        from .native import ADAPTERS, get_adapter  # native imports sync and bootstrap's siblings
        from .native.manifest import native_status

        for tool in (t for t in tools if t in ADAPTERS):
            adapter = get_adapter(tool, project_root)
            native_results[tool] = adapter.run() + [f"AVISO: {w}" for w in adapter.warnings]
        # sync reported the status before the generators ran
        sync_results.update({f"{AOS_DIR_NAME}/native/{t}.json": s for t, s in native_status(project_root).items()})

    return {
        "status": "success",
        "project_name": project_name,
        "project_root": str(project_root),
        "aos_dir": str(aos_dir),
        "tools": tools,
        "sync_results": sync_results,
        "native_results": native_results,
    }
