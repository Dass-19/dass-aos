"""Tests for memory refresh and gotchas."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dass_aos.constants import AOS_DIR_NAME
from dass_aos.memory import list_recent_gotchas, missing_dependencies, run_memory_refresh


class TestMemory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.gotchas_dir = self.temp_dir / AOS_DIR_NAME / "knowledge" / "gotchas"
        self.gotchas_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

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
        with mock.patch("dass_aos.memory.shutil.which", return_value=None):
            names = [name for name, _ in missing_dependencies(self.temp_dir)]
            self.assertEqual(names, ["semgrep", "codebase-memory-mcp"])  # no IaC -> no checkov
            (self.temp_dir / "main.tf").write_text("", encoding="utf-8")
            self.assertIn("checkov", [name for name, _ in missing_dependencies(self.temp_dir)])
        with mock.patch("dass_aos.memory.shutil.which", return_value="/bin/x"):
            self.assertEqual(missing_dependencies(self.temp_dir), [])


if __name__ == "__main__":
    unittest.main()
