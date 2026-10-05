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
        self.assertIn("filesystem", mcp_data["mcpServers"])
        self.assertIn("codebase-memory", mcp_data["mcpServers"])

        # Check instruction files in project root
        self.assertTrue((self.temp_dir / "CLAUDE.md").exists())
        self.assertTrue((self.temp_dir / "AGENTS.md").exists())
        self.assertTrue((self.temp_dir / "GEMINI.md").exists())
        self.assertTrue((self.temp_dir / ".cursorrules").exists())


if __name__ == "__main__":
    unittest.main()
