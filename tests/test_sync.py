"""Tests for agent instruction synchronization."""
import shutil
import tempfile
import unittest
from pathlib import Path

from dass_aos.constants import MANAGED_END, MANAGED_START
from dass_aos.sync import sync_all_instructions, sync_file


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

    def test_sync_all_files(self):
        results = sync_all_instructions(self.temp_dir, create_missing=True)
        self.assertIn("CLAUDE.md", results)
        self.assertIn("AGENTS.md", results)
        self.assertIn("GEMINI.md", results)
        self.assertIn(".cursorrules", results)


if __name__ == "__main__":
    unittest.main()
