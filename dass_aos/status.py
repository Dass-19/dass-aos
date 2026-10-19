"""`aos status`: the state of the work, derived from files (ADR-008).

Four public states, no model in the loop:

- ``Needs decision`` — a recorded question has no answer, or the next phase is discovery/design.
- ``Working`` — implementation is the next thing to do.
- ``Checking`` — implementation is done; the next phase is verification, review or scan.
- ``Ready`` — no unchecked phase left (or no active plan at all): ready to close or to start.

Everything is read from `.aos/plans/active/`, `.aos/specs/` and `aos doctor`; nothing is written.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

from .constants import AOS_DIR_NAME, configure_utf8_output
from .specs import open_specs

NEEDS_DECISION = "Needs decision"
WORKING = "Working"
CHECKING = "Checking"
READY = "Ready"
STATES = (NEEDS_DECISION, WORKING, CHECKING, READY)

DISCOVERY_HINTS = ("discovery", "requisito", "diseño", "diseno", "alcance", "aprob")
CHECKING_HINTS = ("verific", "revisi", "auditor", "prueba en vivo", "live-verify", "scan", "recibo")

_PHASE = re.compile(r"^- \[([ xX])\]\s+(.+)$")
_QUESTION = re.compile(r"\*\*Pregunta:\*\*\s*(.*)")
_DECISION = re.compile(r"\*\*Decisión:\*\*\s*(.*)")
_EMPTY_ANSWERS = {"", "pendiente", "(pendiente)", "?", "tbd", "—", "-"}


@dataclass
class PlanStatus:
    """One active plan as the status command reads it."""

    path: Path
    title: str
    total: int = 0
    done: int = 0
    next_task: Optional[str] = None
    unanswered_questions: int = 0


@dataclass
class StatusReport:
    state: str
    reason: str
    plan: Optional[PlanStatus] = None
    other_plans: int = 0
    open_specs: int = 0
    specs_without_pair: int = 0
    doctor_errors: int = 0
    next_task: Optional[str] = None
    extras: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        data = asdict(self)
        if self.plan:
            data["plan"] = {"path": str(self.plan.path), "title": self.plan.title,
                            "total": self.plan.total, "done": self.plan.done,
                            "unanswered_questions": self.plan.unanswered_questions}
        return data


def count_unanswered_questions(text: str) -> int:
    """A recorded question counts as open until a `Decisión:` with a real answer follows it."""
    unanswered = 0
    open_question = False
    for line in text.splitlines():
        question = _QUESTION.search(line)
        if question:
            if open_question:
                unanswered += 1
            open_question = bool(question.group(1).strip())
            continue
        answer = _DECISION.search(line)
        if answer and open_question and answer.group(1).strip().lower() not in _EMPTY_ANSWERS:
            open_question = False
    return unanswered + (1 if open_question else 0)


def active_plan_files(project_root: Path) -> List[Path]:
    directory = project_root / AOS_DIR_NAME / "plans" / "active"
    if not directory.exists():
        return []
    # NNN-x.design.md is shared context, not a plan (phased-delivery §3)
    return sorted(p for p in directory.glob("*.md") if p.name.lower() != "readme.md" and not p.name.endswith(".design.md"))


def read_plan(path: Path) -> PlanStatus:
    text = path.read_text(encoding="utf-8")
    title = path.stem
    total = done = 0
    next_task: Optional[str] = None
    for line in text.splitlines():
        heading = line.startswith("# ")
        if heading:
            title = line[2:].strip()
            continue
        phase = _PHASE.match(line)
        if not phase:
            continue
        total += 1
        if phase.group(1).lower() == "x":
            done += 1
        elif next_task is None:
            next_task = phase.group(2).strip()
    return PlanStatus(
        path=path,
        title=title,
        total=total,
        done=done,
        next_task=next_task,
        unanswered_questions=count_unanswered_questions(text),
    )


def _is_discovery(task: Optional[str]) -> bool:
    lowered = (task or "").lower()
    return any(hint in lowered for hint in DISCOVERY_HINTS)


def _is_checking(task: Optional[str]) -> bool:
    lowered = (task or "").lower()
    return any(hint in lowered for hint in CHECKING_HINTS)


def derive_state(plan: Optional[PlanStatus]) -> tuple[str, str]:
    """Map file facts to one of the four public states, with a one-line reason."""
    if plan is None:
        return READY, "no hay plan activo: listo para empezar"
    if plan.unanswered_questions:
        return NEEDS_DECISION, f"{plan.unanswered_questions} pregunta(s) registrada(s) sin decisión"
    if plan.total == 0:
        return NEEDS_DECISION, "el plan activo no tiene fases: define alcance antes de trabajar"
    if plan.done == plan.total:
        return READY, f"las {plan.total} fases del plan están completas: listo para cerrar"
    if _is_discovery(plan.next_task):
        return NEEDS_DECISION, f"la siguiente fase pide alcance o requisitos: {plan.next_task}"
    if _is_checking(plan.next_task):
        return CHECKING, f"la siguiente fase es de verificación: {plan.next_task}"
    return WORKING, f"siguiente fase: {plan.next_task}"


def build_report(project_root: Path) -> StatusReport:
    plans = active_plan_files(project_root)
    plan = read_plan(plans[0]) if plans else None
    state, reason = derive_state(plan)

    specs = open_specs(project_root, limit=100)
    without_pair = [s for s in specs if not s.has_counterpart]

    # Imported here: doctor imports sync/memory, and status must stay cheap when unused.
    from .doctor import collect_findings

    doctor_errors = sum(1 for finding in collect_findings(project_root) if finding.level == "error")

    extras: List[str] = []
    if plan and plan.total:
        extras.append(f"{plan.done}/{plan.total} fases completas")
    if without_pair:
        extras.append(f"{len(without_pair)} especificación(es) sin pareja")
    extras.append(f"doctor: {doctor_errors} error(es)")

    return StatusReport(
        state=state,
        reason=reason,
        plan=plan,
        other_plans=max(len(plans) - 1, 0),
        open_specs=len(specs),
        specs_without_pair=len(without_pair),
        doctor_errors=doctor_errors,
        next_task=plan.next_task if plan else None,
        extras=extras,
    )


def run_status(project_root: Path, as_json: bool = False) -> int:
    configure_utf8_output()
    report = build_report(project_root.resolve())
    if as_json:
        # ensure_ascii keeps the output readable for any consumer, including Windows pipes in cp1252.
        print(json.dumps(report.as_dict(), ensure_ascii=True, indent=2, default=str))
        return 0

    print(f"[aos status] {project_root.resolve()}")
    print(f"  Estado: {report.state} — {report.reason}")
    if report.plan:
        others = f" (+{report.other_plans} plan(es) activo(s) más)" if report.other_plans else ""
        print(f"  Plan: {report.plan.title} ({report.plan.path.name}){others}")
    if report.next_task:
        print(f"  Siguiente: {report.next_task}")
    print(f"  Hechos: {' · '.join(report.extras)}")
    return 0
