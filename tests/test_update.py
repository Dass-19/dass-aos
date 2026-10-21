"""Tests for `aos update` (ADR-007 / ADR-008 project upgrade)."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from dass_aos.bootstrap import init_project
from dass_aos.constants import VERSION
from dass_aos.update import run_update, update_project


class TestUpdate(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_update_missing_aos_raises(self):
        with self.assertRaises(FileNotFoundError):
            update_project(self.temp_dir)

    def test_update_bumps_version_and_adds_deny_paths(self):
        init_project(self.temp_dir, project_name="legacy", tools=["claude-code"])
        config_file = self.temp_dir / ".aos" / "config.json"
        data = json.loads(config_file.read_text(encoding="utf-8"))
        data["aos_version"] = "0.5.0"
        data.pop("deny_paths", None)
        config_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

        res = update_project(self.temp_dir)
        self.assertEqual(res["old_version"], "0.5.0")
        self.assertEqual(res["new_version"], VERSION)

        new_data = json.loads(config_file.read_text(encoding="utf-8"))
        self.assertEqual(new_data["aos_version"], VERSION)
        self.assertIn(".env", new_data["deny_paths"])

    def test_update_creates_missing_specs_and_ledger(self):
        init_project(self.temp_dir, project_name="test-project", tools=["claude-code"])
        specs_dir = self.temp_dir / ".aos" / "specs"
        if specs_dir.exists():
            shutil.rmtree(specs_dir)
        ledger_file = self.temp_dir / ".aos" / "knowledge" / "lessons" / "LEDGER.md"
        if ledger_file.exists():
            ledger_file.unlink()

        res = update_project(self.temp_dir)
        self.assertTrue(specs_dir.exists())
        self.assertTrue((specs_dir / "templates" / "prd.md").exists())
        self.assertTrue(ledger_file.exists())
        self.assertTrue(any("LEDGER.md" in ch for ch in res["changes"]))

    def test_update_adds_cost_to_custom_skills(self):
        init_project(self.temp_dir, project_name="custom", tools=["claude-code"])
        custom_skill = self.temp_dir / ".aos" / "skills" / "specs" / "my-custom.md"
        custom_skill.write_text(
            '---\nid: 202610101000\ntype: skill-spec\nstatus: evergreen\nname: "my-custom"\n'
            'description: "test custom skill"\n---\n\n# Custom\n',
            encoding="utf-8",
        )

        update_project(self.temp_dir)
        content = custom_skill.read_text(encoding="utf-8")
        self.assertIn("cost: on-demand", content)

    def test_run_update_cli_returns_zero(self):
        init_project(self.temp_dir, project_name="test-cli", tools=["claude-code"])
        code = run_update(self.temp_dir)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()

