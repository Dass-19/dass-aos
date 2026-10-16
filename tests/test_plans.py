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
        init_project(self.temp_dir, project_name="test-project", tools=["claude-code", "antigravity"])

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

    def test_plan_number_follows_highest_existing_including_archive(self):
        plans = self.temp_dir / ".aos" / "plans"
        (plans / "archive").mkdir(exist_ok=True)
        (plans / "archive" / "001-old.md").write_text("x", encoding="utf-8")
        (plans / "active" / "003-current.md").write_text("x", encoding="utf-8")
        plan_file = create_new_plan(self.temp_dir, template_type="feature", title="Next")
        self.assertEqual(plan_file.name, "004-next.md")


if __name__ == "__main__":
    unittest.main()
