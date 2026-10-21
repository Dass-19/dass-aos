"""Tests for the Claude Code and Antigravity generators (ADR-005)."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dass_aos.bootstrap import init_project
from dass_aos.constants import AOS_DIR_NAME
from dass_aos.native.antigravity import AntigravityAdapter, refresh_hook
from dass_aos.native.claude import ClaudeAdapter
from dass_aos.native.sources import split_frontmatter
from dass_aos.sync import build_managed_block

NEUTRAL = ("mcp:", "shell:", "read", "search", "edit", "write", "web")


class ToolTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.home = self.root / "home"
        (self.root / ".git").mkdir()
        init_project(self.root, project_name="demo", tools=["claude-code", "antigravity"])
        patcher = mock.patch("pathlib.Path.home", return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def front(self, rel):
        return split_frontmatter((self.root / rel).read_text(encoding="utf-8"))[0]


class TestClaudeAdapter(ToolTestCase):
    def test_roles_restricted_by_blocklist_never_neutral_vocabulary(self):
        ClaudeAdapter(self.root).run(yes=True)
        for agent in (self.root / ".claude" / "agents").glob("*.md"):
            for line in self.front(agent.relative_to(self.root)).splitlines():
                if line.startswith(("disallowedTools:", "tools:")):
                    values = [v.strip() for v in line.split(":", 1)[1].split(",")]
                    self.assertFalse([v for v in values if v.startswith(NEUTRAL)], agent.name)
        self.assertNotIn("\ntools:", self.front(".claude/agents/reviewer.md"))  # an allowlist would drop MCP

    def test_reviewer_cannot_edit_but_keeps_shell_and_mcp(self):
        ClaudeAdapter(self.root).run(yes=True)
        line = next(x for x in self.front(".claude/agents/reviewer.md").splitlines() if x.startswith("disallowedTools:"))
        blocked = {v.strip() for v in line.split(":", 1)[1].split(",")}
        self.assertTrue({"Edit", "Write", "NotebookEdit"} <= blocked)
        self.assertFalse({"Bash", "Read", "Grep"} & blocked)
        self.assertFalse([b for b in blocked if b.startswith("mcp__")])
        body = (self.root / ".claude" / "agents" / "reviewer.md").read_text(encoding="utf-8")
        self.assertIn("`git`", body)  # shell:git kept as convention
        self.assertEqual(body.count("DASS-AOS-GENERATED"), 1)

    def test_app_builder_has_no_restriction(self):
        ClaudeAdapter(self.root).run(yes=True)
        self.assertNotIn("disallowedTools", self.front(".claude/agents/app-builder.md"))

    def test_skills_only_applicable_and_without_adapt_native(self):
        ClaudeAdapter(self.root).run(yes=True)
        names = {p.parent.name for p in (self.root / ".claude" / "skills").glob("*/SKILL.md")}
        self.assertIn("live-verify", names)
        self.assertNotIn("adapt-native", names)
        self.assertNotIn("db-migration-check", names)  # applies_when: no migrations here

    def test_session_start_hook_merges_keeping_foreign_settings(self):
        settings = self.root / ".claude" / "settings.local.json"
        settings.parent.mkdir(parents=True)
        foreign = {"matcher": "startup", "hooks": [{"type": "command", "command": "echo hola"}]}
        settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"SessionStart": [foreign]}}), encoding="utf-8")
        ClaudeAdapter(self.root).run(yes=True)
        ClaudeAdapter(self.root).run(yes=True)
        data = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls)"]})
        self.assertEqual(data["hooks"]["SessionStart"][0], foreign)
        self.assertEqual(len(data["hooks"]["SessionStart"]), 2)
        self.assertIn("dass_aos refresh", json.dumps(data["hooks"]["SessionStart"][1]))

    def test_mixed_session_start_group_keeps_user_hook(self):
        settings = self.root / ".claude" / "settings.local.json"
        settings.parent.mkdir(parents=True)
        mixed = {"matcher": "startup", "hooks": [{"command": "python -m dass_aos refresh"}, {"command": "echo USER"}]}
        settings.write_text(json.dumps({"hooks": {"SessionStart": [mixed]}}), encoding="utf-8")
        ClaudeAdapter(self.root).run(yes=True)
        self.assertIn("echo USER", settings.read_text(encoding="utf-8"))

    def test_settings_with_bom_merged_and_invalid_json_untouched(self):
        settings = self.root / ".claude" / "settings.local.json"
        settings.parent.mkdir(parents=True)
        settings.write_bytes("﻿".encode("utf-8") + b'{"permissions": {"deny": ["Read(./.env)"]}}')
        ClaudeAdapter(self.root).run(yes=True)
        data = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(data["permissions"], {"deny": ["Read(./.env)"]})
        self.assertIn("SessionStart", data["hooks"])
        settings.write_text('{"hooks": [', encoding="utf-8")
        adapter = ClaudeAdapter(self.root)
        adapter.run(yes=True)  # no crash: warns and leaves the file alone
        self.assertEqual(settings.read_text(encoding="utf-8"), '{"hooks": [')
        self.assertTrue(any("JSON ilegible" in w for w in adapter.warnings))
        self.assertTrue((self.root / AOS_DIR_NAME / "native" / "claude-code.json").exists())

    def test_pending_hook_change_stays_in_manifest_and_gitignore(self):
        ClaudeAdapter(self.root).run(yes=True)
        settings = self.root / ".claude" / "settings.local.json"
        data = json.loads(settings.read_text(encoding="utf-8"))
        data["hooks"]["SessionStart"][0]["hooks"][0]["command"] = "python -m dass_aos refresh"  # older version of ours
        settings.write_text(json.dumps(data), encoding="utf-8")
        ClaudeAdapter(self.root).run()
        self.assertIn(".claude/settings.local.json", (self.root / ".gitignore").read_text(encoding="utf-8"))

    def test_project_mcp_found_whatever_the_key_spelling(self):
        self.home.mkdir()
        key = str(self.root.resolve()).replace("/", "\\").lower()  # Claude Code may store c:\x, C:/x or c:/x
        (self.home / ".claude.json").write_text(json.dumps({"projects": {key: {"mcpServers": {"context7": {}}}}}), encoding="utf-8")
        self.assertIn("user:context7", list(ClaudeAdapter(self.root.resolve()).registered_mcp()))

    def test_user_mcp_detected_or_left_as_convention(self):
        self.home.mkdir()
        (self.home / ".claude.json").write_text(json.dumps({"mcpServers": {"codebase-memory-mcp": {}}}), encoding="utf-8")
        adapter = ClaudeAdapter(self.root)
        adapter.run(yes=True)
        mcp = json.loads((self.root / AOS_DIR_NAME / "native" / "claude-code.json").read_text(encoding="utf-8"))["mcp"]
        self.assertEqual(mcp, {"codebase-memory": "user:codebase-memory-mcp", "context7": "convention"})
        self.assertTrue(any("context7" in w for w in adapter.warnings))


class TestAntigravityAdapter(ToolTestCase):
    def test_skills_and_hook_but_no_subagent_files(self):
        AntigravityAdapter(self.root).run(yes=True)
        self.assertTrue((self.root / ".agents" / "skills" / "live-verify" / "SKILL.md").exists())
        self.assertFalse((self.root / ".agents" / "agents").exists())
        self.assertFalse((self.root / ".agents" / "mcp_config.json").exists())

    def test_hook_merges_keeping_foreign_hooks(self):
        hooks = self.root / ".agents" / "hooks.json"
        hooks.parent.mkdir(parents=True)
        hooks.write_text(json.dumps({"lint": {"PostToolUse": []}}), encoding="utf-8")
        AntigravityAdapter(self.root).run(yes=True)
        data = json.loads(hooks.read_text(encoding="utf-8"))
        self.assertIn("lint", data)
        self.assertIn("refresh --hook antigravity", data["dass-aos-refresh"]["PreInvocation"][0]["command"])
        data["dass-aos-refresh"]["enabled"] = False  # the user turned it off
        hooks.write_text(json.dumps(data), encoding="utf-8")
        AntigravityAdapter(self.root).run(yes=True)
        self.assertFalse(json.loads(hooks.read_text(encoding="utf-8"))["dass-aos-refresh"]["enabled"])

    def test_cleans_files_left_by_the_skill(self):
        # The skill used to write subagents and a project MCP file that Antigravity never loads
        (self.root / ".agents" / "agents").mkdir(parents=True)
        (self.root / ".agents" / "agents" / "reviewer.md").write_text("<!-- DASS-AOS-GENERATED -->\n", encoding="utf-8")
        (self.root / ".agents" / "mcp_config.json").write_text("{}", encoding="utf-8")
        native = self.root / AOS_DIR_NAME / "native"
        native.mkdir(exist_ok=True)
        (native / "antigravity.json").write_text(json.dumps({"files": [".agents/agents/reviewer.md", ".agents/mcp_config.json"]}), encoding="utf-8")
        adapter = AntigravityAdapter(self.root)
        adapter.run(yes=True)
        self.assertFalse((self.root / ".agents" / "agents" / "reviewer.md").exists())
        # JSON has no marker: it may hold the user's keys, so it is reported, never deleted
        self.assertTrue((self.root / ".agents" / "mcp_config.json").exists())
        self.assertTrue(any("mcp_config.json" in w for w in adapter.warnings))

    def test_managed_block_delegation_lists_read_only_roles(self):
        block = build_managed_block("GEMINI.md", self.root)
        line = next(x for x in block.splitlines() if "enable_write_tools" in x)
        for role in ("reviewer", "adversarial-verifier", "security-auditor"):
            self.assertIn(f"`{role}`", line)
        self.assertNotIn("`app-builder`", line)
        self.assertNotIn("define_subagent", build_managed_block("CLAUDE.md", self.root))


class TestAntigravityRefreshHook(ToolTestCase):
    @staticmethod
    def payload(conversation):
        return json.dumps({"conversationId": conversation, "workspacePaths": ["C:/Users/José/proyecto"]}, ensure_ascii=False).encode("utf-8")

    def test_injects_once_per_conversation(self):
        first = json.loads(refresh_hook(self.root, self.payload("c1")))
        self.assertIn("Refresco", first["injectSteps"][0]["ephemeralMessage"])
        self.assertEqual(refresh_hook(self.root, self.payload("c1")), "{}")
        self.assertIn("injectSteps", refresh_hook(self.root, self.payload("c2")))

    def test_bom_from_the_shell_is_accepted(self):
        self.assertIn("injectSteps", refresh_hook(self.root, "﻿".encode("utf-8") + self.payload("c3")))

    def test_invalid_stdin_never_fails(self):
        self.assertEqual(refresh_hook(self.root, b"no es json"), "{}")
        self.assertEqual(refresh_hook(self.root, b""), "{}")


if __name__ == "__main__":
    unittest.main()
