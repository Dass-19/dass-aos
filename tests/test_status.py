"""Tests for `aos status`: state derived from files, never from a model (ADR-008)."""
import shutil
import tempfile
import unittest
from pathlib import Path

from dass_aos.bootstrap import init_project
from dass_aos.status import (
    CHECKING,
    NEEDS_DECISION,
    READY,
    WORKING,
    build_report,
    count_unanswered_questions,
    derive_state,
    read_plan,
    run_status,
)


def write_plan(root: Path, body: str, name: str = "001-demo.md") -> Path:
    path = root / ".aos" / "plans" / "active" / name
    path.write_text(body, encoding="utf-8")
    return path


class TestStatus(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        init_project(self.temp_dir, project_name="test-project", tools=["claude-code"])
        # `init` ships no active plan: keep the state space clean for each test.
        for path in (self.temp_dir / ".aos" / "plans" / "active").glob("*.md"):
            path.unlink()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_no_plan_is_ready(self):
        report = build_report(self.temp_dir)
        self.assertEqual(report.state, READY)

    def test_implementation_phase_is_working(self):
        write_plan(self.temp_dir, "# Plan\n\n- [ ] Fase 3: Implementación de la API\n- [ ] Fase 4: Verificación en vivo\n")
        self.assertEqual(build_report(self.temp_dir).state, WORKING)

    def test_verification_phase_is_checking(self):
        write_plan(self.temp_dir, "# Plan\n\n- [x] Fase 3: Implementación\n- [ ] Fase 4: Verificación en vivo\n")
        self.assertEqual(build_report(self.temp_dir).state, CHECKING)

    def test_discovery_phase_needs_decision(self):
        write_plan(self.temp_dir, "# Plan\n\n- [ ] Fase 1: Discovery & requisitos\n")
        self.assertEqual(build_report(self.temp_dir).state, NEEDS_DECISION)

    def test_all_phases_done_is_ready(self):
        write_plan(self.temp_dir, "# Plan\n\n- [x] Fase 1: Implementación\n- [x] Fase 2: Verificación\n")
        report = build_report(self.temp_dir)
        self.assertEqual(report.state, READY)
        self.assertIn("completas", report.reason)

    def test_unanswered_question_overrides_everything(self):
        write_plan(
            self.temp_dir,
            "# Plan\n\n- [x] Fase 1: Discovery\n- [ ] Fase 2: Implementación\n\n"
            "## Discovery Trail\n- **Pregunta:** ¿Postgres o SQLite?\n- **Decisión:**\n",
        )
        report = build_report(self.temp_dir)
        self.assertEqual(report.state, NEEDS_DECISION)
        self.assertIn("sin decisión", report.reason)

    def test_answered_question_does_not_block(self):
        write_plan(
            self.temp_dir,
            "# Plan\n\n- [ ] Fase 2: Implementación\n\n"
            "## Discovery Trail\n- **Pregunta:** ¿Postgres o SQLite?\n- **Decisión:** SQLite\n",
        )
        self.assertEqual(build_report(self.temp_dir).state, WORKING)

    def test_question_counter_handles_multiple_blocks(self):
        text = (
            "- **Pregunta:** a\n- **Decisión:** sí\n"
            "- **Pregunta:** b\n- **Decisión:** (pendiente)\n"
            "- **Pregunta:** c\n- **Decisión:**\n"
        )
        self.assertEqual(count_unanswered_questions(text), 2)

    def test_empty_plan_without_phases_needs_decision(self):
        path = write_plan(self.temp_dir, "# Plan vacío\n")
        self.assertEqual(derive_state(read_plan(path))[0], NEEDS_DECISION)

    def test_other_active_plans_are_counted(self):
        write_plan(self.temp_dir, "# Uno\n\n- [ ] Fase 2: Implementación\n", "001-uno.md")
        write_plan(self.temp_dir, "# Dos\n\n- [ ] Fase 2: Implementación\n", "002-dos.md")
        report = build_report(self.temp_dir)
        self.assertEqual(report.other_plans, 1)
        self.assertEqual(report.plan.title, "Uno")  # FIFO: the oldest unfinished plan is current

    def test_specs_without_pair_are_reported(self):
        from dass_aos.specs import create_new_spec

        create_new_spec(self.temp_dir, kind="prd", title="Sola")
        report = build_report(self.temp_dir)
        self.assertEqual(report.open_specs, 1)
        self.assertEqual(report.specs_without_pair, 1)

    def test_json_output_is_machine_readable(self):
        import contextlib
        import io
        import json

        write_plan(self.temp_dir, "# Plan\n\n- [ ] Fase 2: Implementación\n")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(run_status(self.temp_dir, as_json=True), 0)
        data = json.loads(buffer.getvalue())
        self.assertEqual(data["state"], WORKING)
        self.assertEqual(data["plan"]["title"], "Plan")

    def test_status_is_read_only(self):
        write_plan(self.temp_dir, "# Plan\n\n- [ ] Fase 2: Implementación\n")
        before = {p: p.read_bytes() for p in self.temp_dir.rglob("*") if p.is_file()}
        build_report(self.temp_dir)
        after = {p: p.read_bytes() for p in self.temp_dir.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
