"""Tests for security scanning and dry-run."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dass_aos.scanners import run_security_scans


class TestScanners(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_dry_run_returns_zero(self):
        code = run_security_scans(self.temp_dir, tool="all", dry_run=True, strict=False)
        self.assertEqual(code, 0)

    def test_checkov_runs_only_with_iac(self):
        with mock.patch("dass_aos.scanners.run_checkov", return_value=0) as checkov:
            run_security_scans(self.temp_dir, tool="all", dry_run=True)
            checkov.assert_not_called()
            run_security_scans(self.temp_dir, tool="checkov", dry_run=True)
            self.assertEqual(checkov.call_count, 1)  # explicit --tool always runs
            (self.temp_dir / "infra").mkdir()
            (self.temp_dir / "infra" / "main.tf").write_text("", encoding="utf-8")
            run_security_scans(self.temp_dir, tool="all", dry_run=True)
            self.assertEqual(checkov.call_count, 2)


if __name__ == "__main__":
    unittest.main()
