"""Project update/migration engine for DASS-AOS (upgrades .aos/ to installed version)."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Dict, List

from .constants import AOS_DIR_NAME, DEFAULT_DENY_PATHS, TEMPLATES_DIR, VERSION, configure_utf8_output
from .native import ADAPTERS, get_adapter
from .sync import sync_all_instructions, sync_engine_docs
from .ui import Card, bold, dim, green, red, yellow


def update_custom_skill_cost(skill_file: Path) -> bool:
    """Ensure custom project skills have cost: on-demand in their frontmatter."""
    try:
        content = skill_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = skill_file.read_text(encoding="utf-8-sig")

    content = content.lstrip()
    if not content.startswith("---"):
        return False

    m = re.match(r"^---\r?\n(.*?)\r?\n---\s*(.*)$", content, re.DOTALL)
    if not m:
        parts = content.split("---")
        if len(parts) >= 3:
            fm = parts[1].strip()
            body = "---".join(parts[2:]).lstrip()
        else:
            return False
    else:
        fm = m.group(1).strip()
        body = m.group(2).lstrip()

    lines = fm.splitlines()
    if any(line.strip().startswith("cost:") for line in lines):
        return False

    new_lines = []
    inserted = False
    for line in lines:
        new_lines.append(line)
        if not inserted and any(line.strip().startswith(p) for p in ("status:", "type:", "id:")):
            new_lines.append("cost: on-demand")
            inserted = True
    if not inserted:
        new_lines.insert(0, "cost: on-demand")

    new_content = f"---\n{chr(10).join(new_lines)}\n---\n\n{body}\n"
    skill_file.write_text(new_content, encoding="utf-8")
    return True


def update_project(project_root: Path) -> Dict[str, object]:
    """Upgrade an existing project's .aos/ state to the current DASS-AOS version."""
    project_root = project_root.resolve()
    aos_dir = project_root / AOS_DIR_NAME
    if not aos_dir.exists():
        raise FileNotFoundError(f"No existe el directorio .aos/ en {project_root}. Usa 'aos init' primero.")

    changes: List[str] = []

    # 1. Update config.json
    config_file = aos_dir / "config.json"
    if config_file.exists():
        try:
            config = json.loads(config_file.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            config = json.loads(config_file.read_text(encoding="utf-8-sig"))
    else:
        config = {"project_name": project_root.name}

    old_version = config.get("aos_version", "desconocida")
    if old_version != VERSION:
        config["aos_version"] = VERSION
        changes.append(f"versión en config: {old_version} -> {VERSION}")

    if not config.get("deny_paths"):
        config["deny_paths"] = DEFAULT_DENY_PATHS
        changes.append("añadido `deny_paths` (ADR-008 seguridad)")

    tools = config.get("tools") or []
    if not isinstance(tools, list):
        tools = []
    if not tools:
        from .sync import detect_tools
        tools = detect_tools(project_root) or ["claude-code", "antigravity"]
        config["tools"] = tools
        changes.append(f"configuradas tools: {', '.join(tools)}")

    config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")

    # 2. Ensure directory layout
    for sub in [
        "specs/templates",
        "knowledge/lessons",
        "skills/specs",
        "skills/bin",
        "agents",
        "hooks",
        "plans/active",
        "plans/archive",
    ]:
        (aos_dir / sub).mkdir(parents=True, exist_ok=True)

    # 3. Copy missing spec templates
    for f in (TEMPLATES_DIR / "specs").rglob("*"):
        if f.is_file():
            rel = f.relative_to(TEMPLATES_DIR / "specs")
            target = aos_dir / "specs" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(f, target)
                changes.append(f"creada plantilla spec: .aos/specs/{rel}")

    # 4. Copy LEDGER.md if missing
    ledger_target = aos_dir / "knowledge" / "lessons" / "LEDGER.md"
    if not ledger_target.exists():
        ledger_src = TEMPLATES_DIR / "knowledge" / "lessons" / "LEDGER.md"
        shutil.copy2(ledger_src, ledger_target)
        changes.append("creado registro de lecciones: .aos/knowledge/lessons/LEDGER.md")

    # 5. Update pre_commit.py hook
    pre_commit_src = TEMPLATES_DIR / "hooks" / "pre_commit.py"
    pre_commit_target = aos_dir / "hooks" / "pre_commit.py"
    if not pre_commit_target.exists() or pre_commit_target.read_text(encoding="utf-8") != pre_commit_src.read_text(encoding="utf-8"):
        shutil.copy2(pre_commit_src, pre_commit_target)
        changes.append("actualizado hook pre_commit.py (inspección de secretos deny_paths)")

    # 6. Copy canonical skill bin scripts if missing
    for f in (TEMPLATES_DIR / "skills" / "bin").glob("*.py"):
        target = aos_dir / "skills" / "bin" / f.name
        if not target.exists():
            shutil.copy2(f, target)
            changes.append(f"creado helper de skill: .aos/skills/bin/{f.name}")

    # 7. Sync engine docs (ADR-003: skills and agents)
    skipped = sync_engine_docs(project_root)
    for skipped_file, reason in skipped.items():
        changes.append(f"{skipped_file}: {reason}")

    # 8. Check custom skills for cost:
    for sf in (aos_dir / "skills" / "specs").glob("*.md"):
        if not sf.stem.endswith(".local") and update_custom_skill_cost(sf):
            changes.append(f"añadido cost: on-demand a {sf.name}")

    # 9. Clean up empty legacy memory/
    legacy_memory = aos_dir / "memory"
    if legacy_memory.exists() and not any(legacy_memory.iterdir()):
        try:
            legacy_memory.rmdir()
            changes.append("eliminado directorio vacío legado .aos/memory/")
        except Exception:
            pass

    # 10. Sync instruction files
    sync_results = sync_all_instructions(project_root)

    # 11. Run adapt-native for configured tools
    native_results = {}
    for tool in (t for t in tools if t in ADAPTERS):
        adapter = get_adapter(tool, project_root)
        tool_changes = adapter.run(yes=True)
        native_results[tool] = tool_changes + [f"AVISO: {w}" for w in adapter.warnings]

    return {
        "project_name": config.get("project_name", project_root.name),
        "old_version": old_version,
        "new_version": VERSION,
        "changes": changes,
        "sync_results": sync_results,
        "native_results": native_results,
    }


def run_update(project_root: Path) -> int:
    """CLI handler for `aos update`."""
    configure_utf8_output()
    root = project_root.resolve()
    card = Card("Update", root.name)
    card.field("Ruta", dim(str(root)))

    try:
        res = update_project(root)
    except Exception as exc:
        card.line(f"  {red('✖ ERROR')}: {exc}")
        print(card.render())
        return 1

    card.field("Versión", f"{yellow(str(res['old_version']))} -> {green(bold(str(res['new_version'])))}")
    card.empty()

    changes = res["changes"]
    if changes:
        card.line(bold("Mejoras de infraestructura aplicadas:"))
        for ch in changes:
            card.line(f"  {green('✓')} {ch}")
    else:
        card.line(f"  {green('✓')} La infraestructura .aos/ ya estaba al día.")

    card.empty()
    card.line(bold("Instrucciones sincronizadas:"))
    for fname, action in res["sync_results"].items():
        badge = green("✓ " + action) if "ACTUALIZADO" in action else dim("· " + action)
        card.line(f"  {badge:<22} {bold(fname)}")

    for tool, lines in res["native_results"].items():
        if lines:
            card.empty()
            card.line(bold(f"Adaptaciones nativas ({tool}):"))
            for line in lines:
                card.line(f"  · {line}")

    card.empty()
    card.field("Resultado", green(bold("✓ Proyecto actualizado con éxito a v" + str(res["new_version"]))))
    print(card.render())
    return 0
