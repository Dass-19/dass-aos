"""Tests for PRD/TRD spec management (ADR-007)."""
import shutil
import tempfile
import unittest
from pathlib import Path

from dass_aos.bootstrap import init_project
from dass_aos.specs import create_new_spec, open_specs, read_specs


class TestSpecs(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        init_project(self.temp_dir, project_name="test-project", tools=["claude-code"])

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_prd_uses_first_free_number(self):
        spec = create_new_spec(self.temp_dir, kind="prd", title="User Authentication")
        self.assertEqual(spec.name, "001-user-authentication.prd.md")
        content = spec.read_text(encoding="utf-8")
        self.assertIn("type: prd", content)
        self.assertIn("PRD: User Authentication", content)
        self.assertIn("CA-1", content)

    def test_trd_reuses_prd_number_for_same_title(self):
        create_new_spec(self.temp_dir, kind="prd", title="User Authentication")
        trd = create_new_spec(self.temp_dir, kind="trd", title="User Authentication")
        self.assertEqual(trd.name, "001-user-authentication.trd.md")
        self.assertIn("type: trd", trd.read_text(encoding="utf-8"))

    def test_new_title_gets_next_number(self):
        create_new_spec(self.temp_dir, kind="prd", title="One")
        second = create_new_spec(self.temp_dir, kind="trd", title="Two")
        self.assertEqual(second.name, "002-two.trd.md")

    def test_duplicate_spec_is_rejected(self):
        create_new_spec(self.temp_dir, kind="prd", title="Same")
        with self.assertRaises(FileExistsError):
            create_new_spec(self.temp_dir, kind="prd", title="Same")

    def test_read_specs_reports_missing_counterpart(self):
        prd = create_new_spec(self.temp_dir, kind="prd", title="Feature A")
        specs = read_specs(self.temp_dir)
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].kind, "prd")
        self.assertFalse(specs[0].has_counterpart)
        self.assertTrue(prd.exists())

    def test_open_specs_skips_closed(self):
        closed = create_new_spec(self.temp_dir, kind="prd", title="Old")
        closed.write_text(
            closed.read_text(encoding="utf-8").replace("status: draft", "status: closed"),
            encoding="utf-8",
        )
        create_new_spec(self.temp_dir, kind="prd", title="Current")
        titles = [s.title for s in open_specs(self.temp_dir)]
        self.assertEqual(titles, ["PRD: Current"])

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            create_new_spec(self.temp_dir, kind="spec", title="X")


if __name__ == "__main__":
    unittest.main()
