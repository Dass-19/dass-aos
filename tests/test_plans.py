"""Tests for plan management and templates."""
import shutil
import tempfile
import unittest
from pathlib import Path

from dass_aos.bootstrap import init_project
from dass_aos.plans import create_new_plan


class TestPlans(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        init_project(self.temp_dir, project_name="test-project")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_new_feature_plan(self):
        plan_file = create_new_plan(
            self.temp_dir,
            template_type="feature",
            title="User Authentication",
        )
        self.assertTrue(plan_file.exists())
        self.assertTrue(plan_file.name.endswith("-user-authentication.md"))

        content = plan_file.read_text(encoding="utf-8")
        self.assertIn("Plan: Feature — User Authentication", content)
        self.assertIn("tags: [plan/feature]", content)


if __name__ == "__main__":
    unittest.main()
