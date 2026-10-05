"""Motor de sincronización para archivos de instrucciones de agentes."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Dict, List, Optional

from .constants import (
    AGENT_FILES,
    AOS_DIR_NAME,
    ENGINE_ROOT,
    LEGACY_MANAGED_END,
    LEGACY_MANAGED_START,
    MANAGED_END,
    MANAGED_START,
    RULE_FILES,
)


def get_available_agents(project_root: Optional[Path] = None) -> List[str]:
    """Obtiene la lista de roles de agentes disponibles del motor y del proyecto."""
    agents = set()
    engine_agents_dir = ENGINE_ROOT / "agents"
    if engine_agents_dir.exists():
        for p in engine_agents_dir.glob("*.md"):
            agents.add(p.stem)

    if project_root:
        local_agents_dir = project_root / AOS_DIR_NAME / "agents"
        if local_agents_dir.exists():
            for p in local_agents_dir.glob("*.md"):
                agents.add(p.stem)

    return sorted(agents)


def get_available_skills(project_root: Optional[Path] = None) -> List[str]:
    """Obtiene la lista de skills disponibles del motor y del proyecto."""
    skills = set()
    engine_skills_dir = ENGINE_ROOT / "skills" / "specs"
    if engine_skills_dir.exists():
        for p in engine_skills_dir.glob("*.md"):
            skills.add(p.stem)

    if project_root:
        local_skills_dir = project_root / AOS_DIR_NAME / "skills"
        if local_skills_dir.exists():
            for p in local_skills_dir.glob("*.md"):
                skills.add(p.stem)

    # Comandos core del CLI
    cli_skills = [
        "init",
        "refresh",
        "verify",
        "scan",
        "generate-client",
        "plan",
        "sync",
    ]
    for s in cli_skills:
        skills.add(s)

    return sorted(skills)


def build_managed_block(target_file: str, project_root: Path) -> str:
    """Construye el bloque gestionado en Markdown con optimizaciones específicas por herramienta."""
    today = dt.date.today().isoformat()
    agents = get_available_agents(project_root)
    skills = get_available_skills(project_root)

    agents_list_str = ", ".join(f"`{a}`" for a in agents) if agents else "(ninguno definido)"
    skills_list_str = ", ".join(f"`{s}`" for s in skills) if skills else "(ninguno definido)"

    lines = [
        MANAGED_START,
        f"# Instrucciones Gestionadas por DASS-AOS (v0.4.0 · generado {today})",
        "",
        "> **Raíz del Estado del Proyecto**: `.aos/`",
        "> Todas las reglas, planes activos, contratos, decisiones y trampas (gotchas) se almacenan localmente en `.aos/`.",
        "",
        "## Ciclo de Vida Obligatorio del Agente",
        "1. **Inicio de Sesión (Session-Start)**: Ejecutar `python aos.py refresh` (o `aos refresh`) para revisar gotchas recientes y el estado de memoria.",
        "2. **Pre-Tarea (Pre-Task)**: Consultar `.aos/plans/active/` para tomar la siguiente tarea atómica sin marcar. Revisar `.aos/contracts/` y consultar `codebase-memory` antes de modificar código.",
        "3. **En Tarea (In-Task)**: Trabajar en fases atómicas. Nunca inventar endpoints ni esquemas de eventos que no estén formalmente declarados en `.aos/contracts/`.",
        "4. **Post-Tarea (Post-Task)**: Ejecutar `python aos.py verify` (linters/tests) y `python aos.py scan` (Semgrep/Checkov). Marcar la tarea completada en el plan con `[x]`.",
        "",
        "## Roles Especializados Disponibles",
        agents_list_str,
        "",
        "## Skills y Comandos Principales Disponibles",
        skills_list_str,
        "",
        "## Contratos y Codebase Memory",
        "- **Contratos**: Consulta `.aos/contracts/http/`, `.aos/contracts/events/` y `.aos/contracts/schemas/`.",
        "- **Codebase Memory**: Consulta el grafo estructural (`search_graph`/`query_graph`) antes de alterar arquitecturas cruzadas.",
        "- **Trampas (Gotchas)**: Documenta nuevos aprendizajes y trampas en `.aos/knowledge/gotchas/<nombre>.md`.",
        "- **Decisiones (ADRs)**: Cambios arquitectónicos transversales requieren un ADR bajo `.aos/decisions/`.",
    ]

    # Consejos adaptados por herramienta
    if target_file == "CLAUDE.md":
        lines.extend([
            "",
            "## Directivas para Claude Code",
            "- Realiza ediciones atómicas y enfocadas.",
            "- Ejecuta los comandos de verificación directamente antes de declarar tareas como completadas.",
            "- Para escaneos de seguridad en local, utiliza `python aos.py scan --dry-run` si las herramientas no están instaladas.",
        ])
    elif target_file == "GEMINI.md":
        lines.extend([
            "",
            "## Directivas para Gemini / Antigravity",
            "- Aprovecha activamente las herramientas de MCP del filesystem y codebase-memory.",
            "- Sigue estrictamente las fases del plan activo sin saltar pasos de verificación.",
        ])
    elif target_file in RULE_FILES:
        lines.extend([
            "",
            "## Reglas de Editor (Cursor / Windsurf)",
            "- Lee siempre el plan activo en .aos/plans/active/ antes de escribir código.",
            "- Mantén estricta adherencia a los contratos en .aos/contracts/.",
        ])

    lines.extend([
        "",
        "## Aviso de Sincronización",
        "No edites este bloque manualmente. Para resincronizar las instrucciones, ejecuta:",
        "```bash",
        "python aos.py sync",
        "```",
        MANAGED_END,
        "",
    ])

    return "\n".join(lines)


def sync_file(file_path: Path, project_root: Path, create_missing: bool = False) -> bool:
    """Sincroniza un archivo individual de instrucciones de agente."""
    managed_content = build_managed_block(file_path.name, project_root)

    if not file_path.exists():
        if not create_missing:
            return False
        initial_content = (
            f"# {file_path.name} — Instrucciones del Proyecto\n\n"
            f"{managed_content}\n"
            "## Notas personalizadas del proyecto\n\n"
            "(Añade aquí notas libres, detalles específicos del stack y consejos para desarrolladores — se conservarán intactas en cada sincronización)\n"
        )
        file_path.write_text(initial_content, encoding="utf-8")
        return True

    text = file_path.read_text(encoding="utf-8")

    # Detectar delimitadores de bloque (actuales o heredados)
    start_tag = MANAGED_START if MANAGED_START in text else (LEGACY_MANAGED_START if LEGACY_MANAGED_START in text else None)
    end_tag = MANAGED_END if MANAGED_END in text else (LEGACY_MANAGED_END if LEGACY_MANAGED_END in text else None)

    if start_tag and end_tag:
        before = text.split(start_tag)[0]
        after = text.split(end_tag)[-1]
        new_text = before + managed_content + after
    else:
        new_text = managed_content + "\n" + text

    file_path.write_text(new_text, encoding="utf-8")
    return True


def sync_all_instructions(project_root: Path, create_missing: bool = False) -> Dict[str, str]:
    """Sincroniza todos los archivos de instrucciones de agentes en el proyecto destino."""
    results = {}
    target_files = AGENT_FILES + RULE_FILES

    for filename in target_files:
        path = project_root / filename
        existed = path.exists()
        success = sync_file(path, project_root, create_missing=create_missing)
        if success:
            results[filename] = "CREADO" if not existed else "ACTUALIZADO"
        else:
            results[filename] = "OMITIDO"

    return results
