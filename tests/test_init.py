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
        res = init_project(self.temp_dir, project_name="my-demo-app", tools=["claude-code", "antigravity"])
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
        self.assertFalse((aos_dir / "memory").exists())

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
        self.assertNotIn("env", mcp_data["mcpServers"]["codebase-memory"])  # no absolute DB path in a versioned file

        # Only the instruction files of the chosen tools, and the choice is remembered
        self.assertTrue((self.temp_dir / "CLAUDE.md").exists())
        self.assertTrue((self.temp_dir / "GEMINI.md").exists())
        for name in ("AGENTS.md", ".cursorrules", ".windsurfrules"):
            self.assertFalse((self.temp_dir / name).exists(), name)
        self.assertEqual(config_data["tools"], ["claude-code", "antigravity"])

    def test_init_only_antigravity(self):
        res = init_project(self.temp_dir, tools=["antigravity"])
        self.assertEqual(res["tools"], ["antigravity"])
        self.assertEqual(sorted(p.name for p in self.temp_dir.glob("*.md")), ["GEMINI.md"])

    def test_init_without_tools_detects_or_fails(self):
        with self.assertRaises(ValueError) as ctx:
            init_project(self.temp_dir)
        self.assertIn("claude-code", str(ctx.exception))
        self.assertFalse((self.temp_dir / AOS_DIR_NAME).exists())  # nothing written before failing
        (self.temp_dir / ".agents").mkdir()
        (self.temp_dir / ".agents" / "hooks.json").write_text("{}", encoding="utf-8")
        self.assertEqual(init_project(self.temp_dir)["tools"], ["antigravity"])

    def test_shared_agents_skills_folder_is_not_antigravity(self):
        # .agents/skills/ is the agentskills standard (Codex, playwright-cli --skills=agents)
        (self.temp_dir / ".agents" / "skills" / "playwright-cli").mkdir(parents=True)
        (self.temp_dir / "AGENTS.md").write_text("reglas propias\n", encoding="utf-8")
        self.assertEqual(init_project(self.temp_dir)["tools"], ["codex"])
        self.assertFalse((self.temp_dir / "GEMINI.md").exists())

    def test_pre_060_project_files_written_by_aos_are_not_signs(self):
        init_project(self.temp_dir, tools=["claude-code", "antigravity"])
        config = self.temp_dir / AOS_DIR_NAME / "config.json"
        data = json.loads(config.read_text(encoding="utf-8"))
        del data["tools"]  # as before 0.6.0
        config.write_text(json.dumps(data), encoding="utf-8")
        (self.temp_dir / ".cursor").mkdir()  # the only tool really in use
        self.assertEqual(init_project(self.temp_dir)["tools"], ["cursor"])

    def test_bad_config_fails_before_writing_and_names_the_file(self):
        (self.temp_dir / AOS_DIR_NAME).mkdir()
        config = self.temp_dir / AOS_DIR_NAME / "config.json"
        for content in ("{ bad", '{"tools": null}', '{"tools": ["claude"]}', "[]"):
            config.write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                init_project(self.temp_dir, tools=["claude-code"])
            self.assertIn("config.json", str(ctx.exception))
            self.assertEqual(config.read_text(encoding="utf-8"), content)  # left as it was
            self.assertFalse((self.temp_dir / "CLAUDE.md").exists())

    def test_broken_project_role_keeps_git_hook_and_names_the_file(self):
        (self.temp_dir / ".git" / "hooks").mkdir(parents=True)
        init_project(self.temp_dir, tools=["claude-code"])
        (self.temp_dir / AOS_DIR_NAME / "agents" / "mio.md").write_text('---\ndescription: "x"\n', encoding="utf-8")
        (self.temp_dir / ".git" / "hooks" / "pre-commit").unlink()
        with self.assertRaises(ValueError) as ctx:
            init_project(self.temp_dir, native=True)
        self.assertIn("mio.md", str(ctx.exception))
        self.assertTrue((self.temp_dir / ".git" / "hooks" / "pre-commit").exists())

    def test_reinit_reports_native_status_after_generating(self):
        init_project(self.temp_dir, tools=["claude-code"], native=True)
        (self.temp_dir / AOS_DIR_NAME / "agents" / "reviewer.local.md").write_text("- algo\n", encoding="utf-8")
        res = init_project(self.temp_dir, native=True)
        self.assertEqual(res["sync_results"][".aos/native/claude-code.json"], "al día")

    def test_init_adds_a_tool_later_and_rejects_unknown(self):
        init_project(self.temp_dir, tools=["antigravity"])
        self.assertEqual(init_project(self.temp_dir, tools=["claude-code"])["tools"], ["antigravity", "claude-code"])
        self.assertTrue((self.temp_dir / "CLAUDE.md").exists())
        with self.assertRaises(ValueError):
            init_project(self.temp_dir, tools=["vscode"])

    def test_init_native_generates_without_hooks(self):
        res = init_project(self.temp_dir, tools=["antigravity"], native=True)
        self.assertTrue((self.temp_dir / ".agents" / "skills" / "live-verify" / "SKILL.md").exists())
        self.assertFalse((self.temp_dir / ".agents" / "hooks.json").exists())
        self.assertTrue(any("PENDIENTE" in line for line in res["native_results"]["antigravity"]))

    def test_init_copies_all_templates(self):
        init_project(self.temp_dir, project_name="demo", tools=["claude-code", "antigravity"])
        aos_dir = self.temp_dir / AOS_DIR_NAME

        def names(sub):
            return {p.stem for p in (aos_dir / sub).glob("*.md")}

        self.assertEqual(names("agents"), {
            "adversarial-verifier", "app-builder", "architect", "qa-tester", "refactorer", "reviewer",
            "security-auditor",
        })
        self.assertEqual(names("skills/specs"), {
            "adapt-native", "adversarial-review", "api-smoke-test", "bootstrap-project", "checkov-scan",
            "db-migration-check", "generate-client", "git-atomic-commit", "live-verify", "memory-refresh",
            "phased-delivery", "semgrep-scan", "sync-agent-instructions",
        })
        self.assertEqual(names("plans/templates"), {"bugfix", "feature", "refactor", "security"})
        self.assertEqual(names("hooks"), {"session-start", "pre-task", "post-task"})
        self.assertEqual(names("knowledge"), {"backend", "frontend", "security"})

    def test_init_git_hook_does_not_need_aos_py(self):
        (self.temp_dir / ".git" / "hooks").mkdir(parents=True)
        init_project(self.temp_dir, project_name="demo", tools=["claude-code", "antigravity"])
        hook = (self.temp_dir / ".git" / "hooks" / "pre-commit").read_text(encoding="utf-8")
        self.assertNotIn("aos.py", hook)
        self.assertIn(".aos/hooks/pre_commit.py", hook)
        for f in ["CLAUDE.md", "GEMINI.md"]:
            self.assertNotIn("aos.py", (self.temp_dir / f).read_text(encoding="utf-8"))


    def test_init_detects_stack_commands(self):
        (self.temp_dir / "package.json").write_text('{"scripts": {"lint": "eslint .", "test": "jest"}}', encoding="utf-8")
        init_project(self.temp_dir, project_name="demo", tools=["claude-code", "antigravity"])
        config = json.loads((self.temp_dir / AOS_DIR_NAME / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["lint_command"], "npm run lint")
        self.assertEqual(config["test_command"], "npm test")

    def test_init_without_stack_leaves_commands_empty(self):
        init_project(self.temp_dir, project_name="demo", tools=["claude-code", "antigravity"])
        config = json.loads((self.temp_dir / AOS_DIR_NAME / "config.json").read_text(encoding="utf-8"))
        self.assertIsNone(config["lint_command"])
        self.assertIsNone(config["test_command"])


if __name__ == "__main__":
    unittest.main()
