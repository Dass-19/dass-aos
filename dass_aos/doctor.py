"""`aos doctor`: read-only audit of the agent harness this project builds (ADR-008).

It answers one question: does what the agent actually loads match what `.aos/` says it should?
It never writes anything and, by default, never fails a build: diagnosis only (`--strict` turns
error-level findings into a non-zero exit).

The taxonomy it audits comes from Harness² (google-research/harness2): every artifact has a
runtime cost class — always-on prose (the managed block), on-demand (skills), delegated
(subagents) and enforced (hooks). Always-on prose is the expensive one.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .constants import AOS_DIR_NAME, TOOL_FILES, configure_utf8_output
from .memory import missing_dependencies
from .native.manifest import native_status
from .specs import open_specs, read_frontmatter
from .sync import (
    TOOL_VOCABULARY,
    build_managed_block,
    configured_tools,
    get_available_skills,
    validate_tools_allowed,
)
from .ui import (
    Card,
    badge_error,
    badge_info,
    badge_warn,
    bold,
    dim,
    green,
    red,
    yellow,
)

# Always-on prose competes with the agent's output budget; Antigravity caps its rules at 20k tokens.
ALWAYS_ON_WARN_CHARS = 12_000
ALWAYS_ON_ERROR_CHARS = 20_000
CHARS_PER_TOKEN = 4
VALID_COSTS = {"always-on", "on-demand", "enforced", "delegated"}


@dataclass(frozen=True)
class Finding:
    """One diagnostic line: level, area and what to do about it."""

    level: str  # error | warn | info
    area: str
    message: str


def _spec_files(directory: Path) -> List[Path]:
    if not directory.exists():
        return []
    return sorted(p for p in directory.glob("*.md") if not p.stem.endswith(".local"))


def check_skill_frontmatter(project_root: Path) -> List[Finding]:
    """A skill dropped silently at load (missing name/description) is invisible to everyone."""
    out: List[Finding] = []
    directory = project_root / AOS_DIR_NAME / "skills" / "specs"
    for path in _spec_files(directory):
        meta = read_frontmatter(path)
        name = (meta.get("name") or "").strip()
        if not name:
            out.append(Finding("error", path.name, "sin `name:` en el frontmatter: se descarta en silencio al cargar"))
        elif name != path.stem:
            out.append(Finding("error", path.name, f"`name: {name}` no coincide con el archivo: debe ser `{path.stem}`"))
        if not (meta.get("description") or "").strip():
            out.append(Finding("error", path.name, "sin `description:`: la skill no se puede invocar por descripción"))
        cost = (meta.get("cost") or "").strip()
        if not cost:
            out.append(Finding("warn", path.name, "sin `cost:` (always-on | on-demand | enforced | delegated)"))
        elif cost not in VALID_COSTS:
            out.append(Finding("error", path.name, f"`cost: {cost}` no es válido; usa {', '.join(sorted(VALID_COSTS))}"))
    return out


def check_agent_frontmatter(project_root: Path) -> List[Finding]:
    out: List[Finding] = []
    directory = project_root / AOS_DIR_NAME / "agents"
    for path in _spec_files(directory):
        meta = read_frontmatter(path)
        if not (meta.get("description") or "").strip():
            out.append(Finding("error", path.name, "rol sin `description:`"))
        if "tools_allowed" not in meta:
            out.append(Finding("warn", path.name, "rol sin `tools_allowed:` (ver ADR-004)"))
    return out


def check_shadowed_skills(project_root: Path) -> List[Finding]:
    """A skill that never reaches the instructions is work that looks done and isn't.

    An unconditional skill in `.aos/skills/specs/` is always listed; the only way it is not is a
    conditional one (`applies_when`) that does not match this project, which is reported as info.
    A malformed `applies_when` breaks the whole list, so it is an error, never a crash.
    """
    out: List[Finding] = []
    try:
        listed = set(get_available_skills(project_root))
    except (ValueError, json.JSONDecodeError) as exc:
        return [Finding("error", ".aos/skills/specs", f"no se pudo construir la lista de skills: {exc}")]

    directory = project_root / AOS_DIR_NAME / "skills" / "specs"
    for path in _spec_files(directory):
        if path.stem in listed:
            continue
        out.append(Finding("info", path.name, "skill condicional (`applies_when`): ahora no aplica a este proyecto"))
    return out


def check_orphan_locals(project_root: Path) -> List[Finding]:
    """`.local.md` additions with no base file are dead weight the engine never renders."""
    out: List[Finding] = []
    for sub in ("agents", "skills/specs"):
        directory = project_root / AOS_DIR_NAME / sub
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.local.md")):
            base = path.with_name(path.name.replace(".local.md", ".md"))
            if not base.exists():
                out.append(Finding("warn", f"{sub}/{path.name}", "agregados .local.md sin archivo base"))
    return out


def check_always_on_budget(project_root: Path) -> List[Finding]:
    """The managed block is in context on every single turn: its size is a real cost."""
    out: List[Finding] = []
    for tool in configured_tools(project_root):
        filename = TOOL_FILES[tool]
        if not (project_root / filename).exists():
            continue
        try:
            chars = len(build_managed_block(filename, project_root))
        except ValueError as exc:
            out.append(Finding("error", filename, f"no se pudo construir el bloque gestionado: {exc}"))
            continue
        tokens = chars // CHARS_PER_TOKEN
        if chars > ALWAYS_ON_ERROR_CHARS:
            level, note = "error", "por encima del límite de reglas de Antigravity (20k tokens)"
        elif chars > ALWAYS_ON_WARN_CHARS:
            level, note = "warn", "conviene mover detalle a una skill (on-demand)"
        else:
            continue
        out.append(Finding(level, filename, f"bloque gestionado: {chars} caracteres (~{tokens} tokens) — {note}"))
    return out


def check_tools_allowed(project_root: Path) -> List[Finding]:
    try:
        validate_tools_allowed(project_root)
    except ValueError as exc:
        return [Finding("error", ".aos/agents", str(exc).splitlines()[0])]
    return []


def check_native_status(project_root: Path) -> List[Finding]:
    return [
        Finding("warn", f".aos/native/{tool}.json", state)
        for tool, state in native_status(project_root).items()
        if "DESACTUALIZADO" in state
    ]


def check_dependencies(project_root: Path) -> List[Finding]:
    return [Finding("info", "dependencias", f"falta `{name}`: {hint}") for name, hint in missing_dependencies(project_root)]


def check_specs(project_root: Path) -> List[Finding]:
    """A PRD without its TRD is a requirement nobody translated into a plan (ADR-007)."""
    return [
        Finding("warn", f".aos/specs/{spec.path.name}", f"{spec.kind.upper()} sin pareja ({'TRD' if spec.kind == 'prd' else 'PRD'})")
        for spec in open_specs(project_root, limit=100)
        if not spec.has_counterpart
    ]


def check_deny_paths(project_root: Path) -> List[Finding]:
    path = project_root / AOS_DIR_NAME / "config.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list) and not data.get("deny_paths"):
        return [Finding("warn", ".aos/config.json", "sin `deny_paths`: el pre-commit no bloquea secretos (.env, claves)")]
    return []


CHECKS = (
    check_skill_frontmatter,
    check_agent_frontmatter,
    check_shadowed_skills,
    check_orphan_locals,
    check_always_on_budget,
    check_tools_allowed,
    check_native_status,
    check_specs,
    check_deny_paths,
    check_dependencies,
)


def collect_findings(project_root: Path) -> List[Finding]:
    """Run every check; a broken check reports an error instead of taking the audit down with it."""
    findings: List[Finding] = []
    for check in CHECKS:
        try:
            findings.extend(check(project_root))
        except Exception as exc:  # a diagnostic tool must report what it found, not crash on it
            findings.append(Finding("error", check.__name__, f"la comprobación falló: {exc}"))
    order = {"error": 0, "warn": 1, "info": 2}
    return sorted(findings, key=lambda f: (order[f.level], f.area))


def format_doctor_card(project_root: Path, findings: List[Finding], counts: Dict[str, int]) -> str:
    card = Card("Doctor", project_root.name)
    card.field("Ruta", dim(str(project_root)))
    card.field("Modo", dim("solo diagnóstico (read-only, no modifica archivos)"))
    card.empty()

    if not findings:
        card.line(f"  {green('✓')} {bold('Sin hallazgos')}: el harness cargado coincide con lo que declara `.aos/`.")
    else:
        card.line(bold("Hallazgos:"))
        badge_map = {
            "error": badge_error("ERROR"),
            "warn": badge_warn("AVISO"),
            "info": badge_info("INFO"),
        }
        for finding in findings:
            b = badge_map.get(finding.level, badge_info(finding.level.upper()))
            card.line(f"  {b}  {bold(finding.area)}: {finding.message}")

    card.empty()

    summary_parts = []
    if counts["error"] == 0 and counts["warn"] == 0:
        summary_parts.append(green(bold("✓ 0 errores · 0 avisos")))
    else:
        if counts["error"] > 0:
            summary_parts.append(red(bold(f"✖ {counts['error']} error(es)")))
        else:
            summary_parts.append(green("✓ 0 errores"))
        if counts["warn"] > 0:
            summary_parts.append(yellow(bold(f"▲ {counts['warn']} aviso(s)")))
        else:
            summary_parts.append(dim("0 avisos"))

    summary_parts.append(dim(f"{counts['info']} info"))
    card.field("Diagnóstico", " · ".join(summary_parts))
    card.field("Herramientas", dim(f"{', '.join(sorted(TOOL_VOCABULARY))}, shell:<prefijo>, mcp:<servidor>"))

    return card.render()


def run_doctor(project_root: Path, strict: bool = False) -> int:
    """Print the harness audit. Returns 1 only with `strict` and at least one error."""
    configure_utf8_output()
    root = project_root.resolve()
    findings = collect_findings(root)
    counts: Dict[str, int] = {level: 0 for level in ("error", "warn", "info")}
    for finding in findings:
        counts[finding.level] += 1

    print(format_doctor_card(root, findings, counts))
    if counts["error"] and strict:
        return 1
    return 0
