"""Módulo de refresco de memoria e inspección de gotchas al inicio de sesión."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import List, Optional, Tuple

from .constants import AOS_DIR_NAME, configure_utf8_output
from .sync import native_status


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


def get_memory_db_info(project_root: Path) -> List[Tuple[str, int, dt.date]]:
    """Obtiene información sobre las bases de datos locales de codebase-memory."""
    db_dirs = [
        project_root / AOS_DIR_NAME / "memory",
        project_root / "codebase-memory",
    ]
    dbs = []
    for d in db_dirs:
        if d.exists():
            for db_file in d.glob("*.db"):
                size = db_file.stat().st_size
                mtime = dt.datetime.fromtimestamp(db_file.stat().st_mtime, dt.timezone.utc).date()
                dbs.append((db_file.name, size, mtime))
    return dbs


def get_active_plan_info(project_root: Path) -> Optional[Tuple[str, str]]:
    """Encuentra el primer plan activo y su siguiente tarea pendiente."""
    plans_dir = project_root / AOS_DIR_NAME / "plans" / "active"
    if not plans_dir.exists():
        plans_dir = project_root / "plans" / "active"

    if not plans_dir.exists():
        return None

    plans = sorted(p for p in plans_dir.glob("*.md") if p.name.lower() != "readme.md")
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

    dbs = get_memory_db_info(project_root)
    if dbs:
        for name, size, date_val in dbs:
            lines.append(f"- Base de datos del Grafo: `{name}` ({size} bytes, actualizada {date_val.isoformat()})")
        lines.append("- **Guía**: Antes de modificar código, ejecuta `search_graph` o `query_graph` para inspeccionar dependencias entre módulos.")
    else:
        lines.append("- No se encontró base de datos local `.db` aún en `.aos/memory/`.")
        lines.append("- El grafo de memoria se inicializará en la primera ejecución de `codebase-memory-mcp`.")

    lines.extend([
        "",
        "## 3. Plan Activo y Siguiente Tarea",
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
        "## 4. Adaptación Nativa (adapt-native)",
    ])
    status = native_status(project_root)
    if status:
        lines.extend(f"- `{tool}`: {state}" for tool, state in status.items())
    else:
        lines.append("- Ninguna herramienta adaptada aún: ejecuta la skill `adapt-native` en tu herramienta.")

    lines.extend([
        "",
        "---",
        "**Estado de Preparación**: Listo para ejecutar el gate de Pre-Tarea.",
    ])

    output = "\n".join(lines)
    print(output)
    return output
