"""Tests for memory refresh and gotchas."""
import shutil
import tempfile
import unittest
from pathlib import Path

from dass_aos.constants import AOS_DIR_NAME
from dass_aos.memory import list_recent_gotchas, run_memory_refresh


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


if __name__ == "__main__":
    unittest.main()
