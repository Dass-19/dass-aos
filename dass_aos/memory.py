"""Módulo de refresco de memoria e inspección de gotchas al inicio de sesión."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import List, Optional, Tuple

from .constants import AOS_DIR_NAME, configure_utf8_output
from .scanners import check_tool_installed, checkov_applies
from .specs import open_specs
from .native.manifest import native_status

# live-verify's web path (ADR-006) needs playwright-cli only when there is a web frontend
WEB_FRONTEND_GLOBS = ["package.json", "*/package.json", "*.html", "*/*.html"]
NOT_FRONTEND_DIRS = {"htmlcov", "site"}  # coverage and mkdocs output, not an app


def list_recent_gotchas(project_root: Path, limit: int = 5) -> List[Tuple[str, Path, dt.date]]:
    """Obtiene los gotchas más recientes con sus títulos y fechas."""
    gotchas_dir = project_root / AOS_DIR_NAME / "knowledge" / "gotchas"
    if not gotchas_dir.exists():
        gotchas_dir = project_root / "knowledge" / "gotchas"

    if not gotchas_dir.exists():
        return []

    files = [
        p for p in gotchas_dir.glob("*.md")
        if p.name.lower() != "readme.md"
    ]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    results = []
    for g in files[:limit]:
        title = g.stem
        try:
            content = g.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.startswith("title:"):
                    title = line.split(":", 1)[1].strip().strip("\"'")
                    break
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
        except Exception:
            pass
        mtime = dt.datetime.fromtimestamp(g.stat().st_mtime, dt.timezone.utc).date()
        results.append((title, g, mtime))

    return results


def list_recent_lessons(project_root: Path, limit: int = 3) -> List[str]:
    """Most recent rows of `.aos/knowledge/lessons/LEDGER.md` (newest first, as written)."""
    ledger = project_root / AOS_DIR_NAME / "knowledge" / "lessons" / "LEDGER.md"
    if not ledger.exists():
        return []
    lessons: List[str] = []
    try:
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if not line.startswith("|") or line.startswith("|-") or line.startswith("| Fecha"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 4 or not any(cells):
                continue
            if cells[1].lstrip("`").startswith("<"):  # template placeholder row
                continue
            lessons.append(f"**{cells[0]}** · {cells[1]} → {cells[3]} (evidencia: {cells[2]})")
    except OSError:
        return []
    return lessons[:limit]


def get_active_plan_info(project_root: Path) -> Optional[Tuple[str, str]]:
    """Encuentra el primer plan activo y su siguiente tarea pendiente."""
    plans_dir = project_root / AOS_DIR_NAME / "plans" / "active"
    if not plans_dir.exists():
        plans_dir = project_root / "plans" / "active"

    if not plans_dir.exists():
        return None

    # NNN-x.design.md sorts before NNN-x.md and is shared context, not a plan (phased-delivery §3)
    plans = sorted(
        p for p in plans_dir.glob("*.md") if p.name.lower() != "readme.md" and not p.name.endswith(".design.md")
    )
    if not plans:
        return None

    first_plan = plans[0]
    plan_title = first_plan.stem
    next_task = "(no hay tareas pendientes)"

    try:
        content = first_plan.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("# "):
                plan_title = line[2:].strip()
            elif line.strip().startswith("- [ ]") and next_task == "(no hay tareas pendientes)":
                next_task = line.strip()[5:].strip()
    except Exception:
        pass

    return (f"{plan_title} ({first_plan.name})", next_task)


def missing_dependencies(project_root: Path) -> List[Tuple[str, str]]:
    """External tools that apply to this project but are not on PATH (warn only, never fail)."""
    deps = [
        ("semgrep", "pip install dass-aos[scan] (o pip install semgrep)"),
        ("codebase-memory-mcp", "ver README, sección Dependencias externas"),
    ]
    if checkov_applies(project_root):
        deps.append(("checkov", "pip install dass-aos[scan] (o pip install checkov)"))
    missing = [(name, hint) for name, hint in deps if not check_tool_installed(name)]
    # ponytail: shallow globs, a web app nested deeper than one folder goes undetected
    if any(
        p.relative_to(project_root).parts[0] not in NOT_FRONTEND_DIRS
        for g in WEB_FRONTEND_GLOBS
        for p in project_root.glob(g)
    ):
        if not check_tool_installed("playwright-cli"):
            missing.append(("playwright-cli", "npm install -g @playwright/cli@latest && playwright-cli install --skills -g"))
        elif (project_root / AOS_DIR_NAME / "native" / "claude-code.json").exists() and not any(
            (base / ".claude" / "skills" / "playwright-cli").exists() for base in (Path.home(), project_root)
        ):
            missing.append(("skill playwright-cli (Claude Code)", "playwright-cli install --skills -g"))
    return missing


def run_memory_refresh(project_root: Path, gotchas_limit: int = 5) -> str:
    """Ejecuta el refresco de inicio de sesión y devuelve el resumen en Markdown."""
    configure_utf8_output()
    now_str = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# DASS-AOS · Refresco de Memoria al Inicio de Sesión",
        f"_Marca de tiempo: {now_str}_",
        "",
        "## 1. Trampas y Gotchas Recientes",
    ]

    gotchas = list_recent_gotchas(project_root, gotchas_limit)
    if not gotchas:
        lines.append("- (No hay gotchas registrados aún. Documenta trampas en `.aos/knowledge/gotchas/` a medida que las descubras)")
    else:
        for title, path, date_val in gotchas:
            lines.append(f"- **{title}** (`{path.name}`, {date_val.isoformat()})")

    lines.extend([
        "",
        "## 2. Estado de Memoria del Código (Codebase Memory)",
    ])

    lines.append("- codebase-memory indexa cada proyecto en la base de datos del usuario (no en `.aos/`). Si `search_graph` no encuentra este proyecto, ejecuta `index_repository` con su ruta.")
    lines.append("- **Guía**: Antes de modificar código, ejecuta `search_graph` o `query_graph` para inspeccionar dependencias entre módulos.")

    lines.extend([
        "",
        "## 3. Especificaciones Abiertas (PRD / TRD)",
    ])

    specs = open_specs(project_root)
    if not specs:
        lines.append("- Ninguna. Crea una con `aos spec new prd --title <titulo>` antes de escribir contratos (ADR-007).")
    else:
        for spec in specs:
            missing = "" if spec.has_counterpart else " · **falta su pareja**"
            lines.append(f"- **{spec.kind.upper()}** {spec.title} (`{spec.path.name}`, {spec.status}){missing}")
        if any(not s.has_counterpart for s in specs):
            lines.append("- La pareja se crea con el mismo título: `aos spec new prd|trd --title \"<titulo>\"` (reutiliza el NNN).")

    lines.extend([
        "",
        "## 4. Plan Activo y Siguiente Tarea",
    ])

    plan_info = get_active_plan_info(project_root)
    if plan_info:
        plan_title, next_task = plan_info
        lines.append(f"- **Plan Activo**: {plan_title}")
        lines.append(f"- **Siguiente Tarea**: {next_task}")
    else:
        lines.append("- No se encontraron planes activos en `.aos/plans/active/`.")
        lines.append("- Crea uno ejecutando `aos plan new feature --title <titulo>`.")

    lines.extend([
        "",
        "## 5. Adaptación Nativa (adapt-native)",
    ])
    status = native_status(project_root)
    if status:
        lines.extend(f"- `{tool}`: {state}" for tool, state in status.items())
    else:
        lines.append("- Ninguna herramienta adaptada aún: `aos adapt-native claude-code --yes` / `aos adapt-native antigravity --yes`, o la skill `adapt-native` en otras herramientas.")

    lines.extend([
        "",
        "## 6. Lecciones Recientes",
    ])
    lessons = list_recent_lessons(project_root)
    if lessons:
        lines.extend(f"- {lesson}" for lesson in lessons)
    else:
        lines.append("- Ninguna. Las lecciones con evidencia se anotan en `.aos/knowledge/lessons/LEDGER.md` al cerrar una fase.")

    lines.extend(["", "## 7. Dependencias Externas"])
    missing = missing_dependencies(project_root)
    if missing:
        lines.extend(f"- Falta `{name}`: {hint}" for name, hint in missing)
    else:
        lines.append("- Todas las dependencias que aplican están instaladas.")

    lines.extend([
        "",
        "---",
        "**Estado de Preparación**: Listo para ejecutar el gate de Pre-Tarea.",
    ])

    output = "\n".join(lines)
    print(output)
    return output
