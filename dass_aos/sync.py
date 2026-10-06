"""Motor de sincronización para archivos de instrucciones de agentes."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Dict, List, Optional

from .constants import (
    AGENT_FILES,
    AOS_DIR_NAME,
    LEGACY_MANAGED_END,
    LEGACY_MANAGED_START,
    MANAGED_END,
    MANAGED_START,
    RULE_FILES,
    TEMPLATES_DIR,
    VERSION,
)


GENERATED_MARKER = "<!-- DASS-AOS-GENERATED"
ENGINE_DOC_DIRS = ["agents", "skills/specs"]


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n")


def _is_local(path: Path) -> bool:
    return path.stem.endswith(".local")


def render_engine_doc(template: Path, local: Path) -> str:
    """Engine template + marker after the frontmatter + optional project additions."""
    text = _norm(template.read_text(encoding="utf-8"))
    marker = f"{GENERATED_MARKER}: no editar; agregados del proyecto en {local.name} -->"
    end = text.find("\n---\n", 4) if text.startswith("---\n") else -1
    if end != -1:
        text = text[: end + 5] + "\n" + marker + "\n" + text[end + 5 :]
    else:
        text = marker + "\n\n" + text
    if local.exists():
        extra = _norm(local.read_text(encoding="utf-8")).strip()
        text = text.rstrip("\n") + f"\n\n## Agregados del proyecto ({local.name})\n\n{extra}\n"
    return text


def sync_engine_docs(project_root: Path) -> Dict[str, str]:
    """Regenerate engine-owned agents/skill specs in .aos/ (ADR-003). Returns only skipped files."""
    skipped = {}
    aos_dir = project_root / AOS_DIR_NAME
    if not aos_dir.exists():
        return skipped
    for sub in ENGINE_DOC_DIRS:
        for template in sorted((TEMPLATES_DIR / sub).glob("*.md")):
            target = aos_dir / sub / template.name
            local = target.with_name(f"{template.stem}.local.md")
            if target.exists():
                current = _norm(target.read_text(encoding="utf-8"))
                pristine = current == _norm(template.read_text(encoding="utf-8"))
                if GENERATED_MARKER not in current and not pristine:
                    skipped[f"{AOS_DIR_NAME}/{sub}/{template.name}"] = (
                        f"OMITIDO: editado a mano; mueve tus cambios a {local.name} y borra el archivo"
                    )
                    continue
            content = render_engine_doc(template, local)
            if not target.exists() or _norm(target.read_text(encoding="utf-8")) != content:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content.encode("utf-8"))
    return skipped


def skill_applies(spec: Path, project_root: Path) -> bool:
    """True unless the spec declares `applies_when: [globs]` and none matches."""
    for line in spec.read_text(encoding="utf-8").splitlines():
        if line.startswith("applies_when:"):
            patterns = json.loads(line.split(":", 1)[1])
            # ponytail: plain Path.glob, keep patterns shallow; add ignore dirs if a ** pattern gets slow
            return any(next(project_root.glob(p), None) for p in patterns)
    return True


def get_available_agents(project_root: Optional[Path] = None) -> List[str]:
    """Obtiene la lista de roles de agentes disponibles del motor y del proyecto."""
    agents = {p.stem for p in (TEMPLATES_DIR / "agents").glob("*.md")}
    if project_root:
        agents |= {p.stem for p in (project_root / AOS_DIR_NAME / "agents").glob("*.md") if not _is_local(p)}
    return sorted(agents)


def get_available_skills(project_root: Optional[Path] = None) -> List[str]:
    """Skills del motor y del proyecto que aplican al proyecto, más los comandos core del CLI."""
    specs = {p.stem: p for p in (TEMPLATES_DIR / "skills" / "specs").glob("*.md")}
    if project_root:
        local_dir = project_root / AOS_DIR_NAME / "skills"
        for p in list((local_dir / "specs").glob("*.md")) or list(local_dir.glob("*.md")):
            specs[p.stem] = p

    skills = {
        name for name, p in specs.items()
        if not _is_local(p) and (project_root is None or skill_applies(p, project_root))
    }
    # Comandos core del CLI
    skills |= {"init", "refresh", "verify", "scan", "plan", "sync"}
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
        f"# Instrucciones Gestionadas por DASS-AOS (v{VERSION} · generado {today})",
        "",
        "> **Raíz del Estado del Proyecto**: `.aos/`",
        "> Todas las reglas, planes activos, contratos, decisiones y trampas (gotchas) se almacenan localmente en `.aos/`.",
        "",
        "## Ciclo de Vida Obligatorio del Agente",
        "1. **Inicio de Sesión (Session-Start)**: Ejecutar `aos refresh` (o `python -m dass_aos refresh`) para revisar gotchas recientes y el estado de memoria.",
        "2. **Pre-Tarea (Pre-Task)**: Consultar `.aos/plans/active/` para tomar la siguiente tarea atómica sin marcar. Revisar `.aos/contracts/` y consultar `codebase-memory` antes de modificar código.",
        "3. **En Tarea (In-Task)**: Trabajar en fases atómicas. Nunca inventar endpoints ni esquemas de eventos que no estén formalmente declarados en `.aos/contracts/`.",
        "4. **Post-Tarea (Post-Task)**: Ejecutar `aos verify` (linters/tests) y `aos scan` (Semgrep/Checkov). Marcar la tarea completada en el plan con `[x]`.",
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
        "- **Roles de Agentes**: Consulta directivas y límites en `.aos/agents/<rol>.md`.",
        "- **Ciclo de Vida (Hooks)**: Consulta especificaciones en `.aos/hooks/` (`session-start.md`, `pre-task.md`, `post-task.md`).",
        "- **Skills y Herramientas**: Consulta especificaciones en `.aos/skills/specs/` y utilidades en `.aos/skills/bin/`.",
    ]

    # Consejos adaptados por herramienta
    if target_file == "CLAUDE.md":
        lines.extend([
            "",
            "## Directivas para Claude Code",
            "- Realiza ediciones atómicas y enfocadas.",
            "- Ejecuta los comandos de verificación directamente antes de declarar tareas como completadas.",
            "- Para escaneos de seguridad en local, utiliza `aos scan --dry-run` si las herramientas no están instaladas.",
        ])
    elif target_file == "GEMINI.md":
        lines.extend([
            "",
            "## Directivas para Gemini / Antigravity",
            "- Aprovecha activamente las herramientas MCP de codebase-memory.",
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
        "aos sync",
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
        after = text.split(end_tag)[-1].lstrip("\r\n")
        # Same layout as a freshly created file: block, one blank line, human notes
        new_text = before + managed_content + ("\n" + after if after else "")
    else:
        new_text = managed_content + "\n" + text

    file_path.write_text(new_text, encoding="utf-8")
    return True


def sync_all_instructions(project_root: Path, create_missing: bool = False) -> Dict[str, str]:
    """Sincroniza todos los archivos de instrucciones de agentes en el proyecto destino."""
    results = sync_engine_docs(project_root)
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
