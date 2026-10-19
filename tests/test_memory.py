"""Tests for memory refresh and gotchas."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dass_aos.constants import AOS_DIR_NAME
from dass_aos.memory import list_recent_gotchas, list_recent_lessons, missing_dependencies, run_memory_refresh


class TestMemory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.gotchas_dir = self.temp_dir / AOS_DIR_NAME / "knowledge" / "gotchas"
        self.gotchas_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_lessons_ledger_skips_header_and_placeholders(self):
        lessons_dir = self.temp_dir / AOS_DIR_NAME / "knowledge" / "lessons"
        lessons_dir.mkdir(parents=True, exist_ok=True)
        (lessons_dir / "LEDGER.md").write_text(
            "| Fecha | Artefacto tocado | Evidencia | Efecto |\n"
            "|---|---|---|---|\n"
            "| 2026-01-01 | `<artefacto>` | `<comando>` | `<efecto>` |\n"
            "| 2026-10-19 | `dass_aos/doctor.py` | `aos doctor` (0 errores) | Un check honesto no genera ruido |\n",
            encoding="utf-8",
        )
        lessons = list_recent_lessons(self.temp_dir)
        self.assertEqual(len(lessons), 1)
        self.assertIn("dass_aos/doctor.py", lessons[0])
        self.assertIn("Un check honesto", lessons[0])
        self.assertNotIn("<artefacto>", lessons[0])

    def test_gotchas_extraction_and_utf8(self):
        # Create a gotcha with utf-8 / accents and arrows
        gotcha_file = self.gotchas_dir / "async-outbox-trap.md"
        gotcha_file.write_text(
            "---\n"
            "title: 'Trampa del Outbox sin drenar'\n"
            "---\n\n"
            "# Trampa del Outbox\n"
            "No olvidar drenar los eventos -> de lo contrario hay inconsistencia.\n",
            encoding="utf-8",
        )

        gotchas = list_recent_gotchas(self.temp_dir, limit=5)
        self.assertEqual(len(gotchas), 1)
        self.assertEqual(gotchas[0][0], "Trampa del Outbox sin drenar")

        # Run memory refresh without throwing UnicodeEncodeError
        output = run_memory_refresh(self.temp_dir)
        self.assertIn("Trampa del Outbox sin drenar", output)
        self.assertIn("async-outbox-trap.md", output)

    def test_missing_dependencies_only_when_they_apply(self):
        with mock.patch("dass_aos.memory.check_tool_installed", return_value=None):
            names = [name for name, _ in missing_dependencies(self.temp_dir)]
            self.assertEqual(names, ["semgrep", "codebase-memory-mcp"])  # no IaC -> no checkov
            (self.temp_dir / "main.tf").write_text("", encoding="utf-8")
            self.assertIn("checkov", [name for name, _ in missing_dependencies(self.temp_dir)])
        with mock.patch("dass_aos.memory.check_tool_installed", return_value="/bin/x"):
            self.assertEqual(missing_dependencies(self.temp_dir), [])

    def test_design_doc_is_not_the_active_plan(self):
        active = self.temp_dir / AOS_DIR_NAME / "plans" / "active"
        active.mkdir(parents=True)
        (active / "001-x.design.md").write_text("# Diseño X\n", encoding="utf-8")
        (active / "001-x.md").write_text("# Plan X\n- [ ] Fase 1: algo\n", encoding="utf-8")
        output = run_memory_refresh(self.temp_dir)
        self.assertIn("001-x.md)", output)
        self.assertNotIn("001-x.design.md", output)

    def test_playwright_cli_only_with_web_frontend(self):
        def names():
            return [name for name, _ in missing_dependencies(self.temp_dir)]

        with mock.patch("dass_aos.memory.check_tool_installed", return_value=None):
            self.assertNotIn("playwright-cli", names())
            (self.temp_dir / "htmlcov").mkdir()
            (self.temp_dir / "htmlcov" / "index.html").write_text("", encoding="utf-8")
            self.assertNotIn("playwright-cli", names())  # coverage report is not a frontend
            (self.temp_dir / "web").mkdir()
            (self.temp_dir / "web" / "package.json").write_text("{}", encoding="utf-8")
            self.assertIn("playwright-cli", names())
        # CLI present, Claude Code adapted, skill nowhere -> warn about the skill
        native = self.temp_dir / AOS_DIR_NAME / "native"
        native.mkdir(parents=True)
        (native / "claude-code.json").write_text("{}", encoding="utf-8")
        with mock.patch("dass_aos.memory.check_tool_installed", return_value="/bin/x"), \
                mock.patch("dass_aos.memory.Path.home", return_value=self.temp_dir / "home"):
            self.assertEqual(names(), ["skill playwright-cli (Claude Code)"])
            (self.temp_dir / ".claude" / "skills" / "playwright-cli").mkdir(parents=True)
            self.assertEqual(names(), [])


if __name__ == "__main__":
    unittest.main()
