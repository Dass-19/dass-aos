"""Tests for project bootstrap and initialization."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from dass_aos.bootstrap import init_project
from dass_aos.constants import AOS_DIR_NAME


class TestBootstrap(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_project_creates_structure(self):
        res = init_project(self.temp_dir, project_name="my-demo-app")
        self.assertEqual(res["status"], "success")

        aos_dir = self.temp_dir / AOS_DIR_NAME
        self.assertTrue(aos_dir.exists())
        self.assertTrue((aos_dir / "contracts" / "http").exists())
        self.assertTrue((aos_dir / "contracts" / "events").exists())
        self.assertTrue((aos_dir / "contracts" / "schemas").exists())
        self.assertTrue((aos_dir / "contracts" / "schemas" / "README.md").exists())
        self.assertTrue((aos_dir / "contracts" / "README.md").exists())
        self.assertTrue((aos_dir / "agents" / "architect.md").exists())
        self.assertTrue((aos_dir / "hooks" / "session-start.md").exists())
        self.assertTrue((aos_dir / "hooks" / "pre_commit.py").exists())
        self.assertTrue((aos_dir / "skills" / "specs" / "semgrep-scan.md").exists())
        self.assertTrue((aos_dir / "skills" / "bin" / "git_atomic_commit.py").exists())
        self.assertTrue((aos_dir / "security" / "scanners" / "README.md").exists())
        self.assertTrue((aos_dir / "plans" / "active").exists())
        self.assertTrue((aos_dir / "knowledge" / "gotchas").exists())
        self.assertTrue((aos_dir / "decisions").exists())
        self.assertTrue((aos_dir / "decisions" / "ADR-001-plantilla.md").exists())
        self.assertFalse((aos_dir / "decisions" / "ADR-002-hibrido-cli-estado-local.md").exists())
        self.assertTrue((aos_dir / "memory").exists())

        # Check config.json
        config_path = aos_dir / "config.json"
        self.assertTrue(config_path.exists())
        config_data = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(config_data["project_name"], "my-demo-app")

        # Check mcp-config.json
        mcp_path = aos_dir / "mcp-config.json"
        self.assertTrue(mcp_path.exists())
        mcp_data = json.loads(mcp_path.read_text(encoding="utf-8"))
        self.assertNotIn("filesystem", mcp_data["mcpServers"])
        self.assertIn("codebase-memory", mcp_data["mcpServers"])
        self.assertIn("url", mcp_data["mcpServers"]["context7"])

        # Check instruction files in project root
        self.assertTrue((self.temp_dir / "CLAUDE.md").exists())
        self.assertTrue((self.temp_dir / "AGENTS.md").exists())
        self.assertTrue((self.temp_dir / "GEMINI.md").exists())
        self.assertTrue((self.temp_dir / ".cursorrules").exists())

    def test_init_copies_all_templates(self):
        init_project(self.temp_dir, project_name="demo")
        aos_dir = self.temp_dir / AOS_DIR_NAME

        def names(sub):
            return {p.stem for p in (aos_dir / sub).glob("*.md")}

        self.assertEqual(names("agents"), {
            "app-builder", "architect", "qa-tester", "refactorer", "reviewer", "security-auditor",
        })
        self.assertEqual(names("skills/specs"), {
            "api-smoke-test", "bootstrap-project", "checkov-scan", "db-migration-check",
            "generate-client", "git-atomic-commit", "memory-refresh", "semgrep-scan",
            "sync-agent-instructions",
        })
        self.assertEqual(names("plans/templates"), {"bugfix", "feature", "refactor", "security"})
        self.assertEqual(names("hooks"), {"session-start", "pre-task", "post-task"})
        self.assertEqual(names("knowledge"), {"backend", "frontend", "security"})

    def test_init_git_hook_does_not_need_aos_py(self):
        (self.temp_dir / ".git" / "hooks").mkdir(parents=True)
        init_project(self.temp_dir, project_name="demo")
        hook = (self.temp_dir / ".git" / "hooks" / "pre-commit").read_text(encoding="utf-8")
        self.assertNotIn("aos.py", hook)
        self.assertIn(".aos/hooks/pre_commit.py", hook)
        for f in ["CLAUDE.md", "AGENTS.md"]:
            self.assertNotIn("aos.py", (self.temp_dir / f).read_text(encoding="utf-8"))


    def test_init_detects_stack_commands(self):
        (self.temp_dir / "package.json").write_text('{"scripts": {"lint": "eslint .", "test": "jest"}}', encoding="utf-8")
        init_project(self.temp_dir, project_name="demo")
        config = json.loads((self.temp_dir / AOS_DIR_NAME / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["lint_command"], "npm run lint")
        self.assertEqual(config["test_command"], "npm test")

    def test_init_without_stack_leaves_commands_empty(self):
        init_project(self.temp_dir, project_name="demo")
        config = json.loads((self.temp_dir / AOS_DIR_NAME / "config.json").read_text(encoding="utf-8"))
        self.assertIsNone(config["lint_command"])
        self.assertIsNone(config["test_command"])


if __name__ == "__main__":
    unittest.main()
