"""Tests for security scanning and dry-run."""
import shutil
import tempfile
import unittest
from pathlib import Path

from dass_aos.scanners import run_security_scans


class TestScanners(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_dry_run_returns_zero(self):
        code = run_security_scans(self.temp_dir, tool="all", dry_run=True, strict=False)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
