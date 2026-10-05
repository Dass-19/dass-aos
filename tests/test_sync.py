"""Tests for agent instruction synchronization."""
import shutil
import tempfile
import unittest
from pathlib import Path

from unittest import mock

from dass_aos.bootstrap import init_project
from dass_aos.constants import MANAGED_END, MANAGED_START, TEMPLATES_DIR
from dass_aos.sync import GENERATED_MARKER, sync_all_instructions, sync_file


class TestSync(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sync_preserves_custom_notes(self):
        claude_md = self.temp_dir / "CLAUDE.md"
        # First sync (creation)
        sync_file(claude_md, self.temp_dir, create_missing=True)
        self.assertTrue(claude_md.exists())

        # Append custom human notes
        original_text = claude_md.read_text(encoding="utf-8")
        custom_note = "\n- Never touch the legacy billing table directly!\n- Python 3.11 is used here.\n"
        claude_md.write_text(original_text + custom_note, encoding="utf-8")

        # Second sync
        sync_file(claude_md, self.temp_dir, create_missing=False)
        updated_text = claude_md.read_text(encoding="utf-8")

        # Verify managed block is present and human note was preserved
        self.assertIn(MANAGED_START, updated_text)
        self.assertIn(MANAGED_END, updated_text)
        self.assertIn("Never touch the legacy billing table directly!", updated_text)
        self.assertIn("Python 3.11 is used here.", updated_text)

    def test_sync_is_idempotent(self):
        claude_md = self.temp_dir / "CLAUDE.md"
        sync_file(claude_md, self.temp_dir, create_missing=True)
        first = claude_md.read_text(encoding="utf-8")
        sync_file(claude_md, self.temp_dir)
        sync_file(claude_md, self.temp_dir)
        self.assertEqual(claude_md.read_text(encoding="utf-8"), first)

    def test_sync_all_files(self):
        results = sync_all_instructions(self.temp_dir, create_missing=True)
        self.assertIn("CLAUDE.md", results)
        self.assertIn("AGENTS.md", results)
        self.assertIn("GEMINI.md", results)
        self.assertIn(".cursorrules", results)


class TestEngineDocs(unittest.TestCase):
    """ADR-003: engine base + project .local.md additions, conditional skills."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        init_project(self.temp_dir, project_name="demo")
        self.agents = self.temp_dir / ".aos" / "agents"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_local_additions_are_appended_and_listed_once(self):
        self.assertIn(GENERATED_MARKER, (self.agents / "architect.md").read_text(encoding="utf-8"))
        (self.agents / "architect.local.md").write_text("Usamos Postgres 16.", encoding="utf-8")
        sync_all_instructions(self.temp_dir)
        text = (self.agents / "architect.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("# Rol:", text)
        self.assertIn("## Agregados del proyecto (architect.local.md)", text)
        self.assertIn("Usamos Postgres 16.", text)
        claude = (self.temp_dir / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertNotIn("architect.local", claude)

    def test_engine_template_changes_propagate(self):
        engine = self.temp_dir / "engine"
        shutil.copytree(TEMPLATES_DIR, engine)
        reviewer = engine / "agents" / "reviewer.md"
        reviewer.write_text(reviewer.read_text(encoding="utf-8") + "\nRegla nueva del motor.\n", encoding="utf-8")
        with mock.patch("dass_aos.sync.TEMPLATES_DIR", engine):
            sync_all_instructions(self.temp_dir)
        self.assertIn("Regla nueva del motor.", (self.agents / "reviewer.md").read_text(encoding="utf-8"))

    def test_hand_edited_file_is_not_overwritten(self):
        edited = self.agents / "qa-tester.md"
        edited.write_text("mis cambios", encoding="utf-8")
        results = sync_all_instructions(self.temp_dir)
        self.assertEqual(edited.read_text(encoding="utf-8"), "mis cambios")
        self.assertIn("OMITIDO", results[".aos/agents/qa-tester.md"])

    def test_conditional_skill_listed_only_when_it_applies(self):
        claude = self.temp_dir / "CLAUDE.md"
        self.assertNotIn("db-migration-check", claude.read_text(encoding="utf-8"))
        self.assertIn("generate-client", claude.read_text(encoding="utf-8"))
        (self.temp_dir / "migrations").mkdir()
        sync_all_instructions(self.temp_dir)
        self.assertIn("db-migration-check", claude.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
