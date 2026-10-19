"""Tests for adapt-native manifests, staleness detection and the generator base (ADR-004, ADR-005)."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from dass_aos.bootstrap import init_project
from dass_aos.constants import AOS_DIR_NAME
from dass_aos.native import get_adapter
from dass_aos.native.base import JsonMerge, NativeAdapter
from dass_aos.native.manifest import native_source_hash, native_status
from dass_aos.sync import sync_all_instructions


class TestNative(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / ".git").mkdir()
        init_project(self.root, project_name="demo", tools=["claude-code", "antigravity"])
        self.native = self.root / AOS_DIR_NAME / "native"
        self.native.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write_manifest(self, source_hash):
        (self.native / "claude-code.json").write_text(json.dumps({"source_hash": source_hash}), encoding="utf-8")

    def test_init_ignores_native_dir_once(self):
        init_project(self.root, project_name="demo", tools=["claude-code", "antigravity"])
        lines = (self.root / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines.count(".aos/native/"), 1)
        self.assertEqual(lines.count(".playwright-cli/"), 1)

    def test_sync_adds_missing_gitignore_entries_keeping_line_endings(self):
        # Projects created before an entry existed get it on `aos sync`; LF files stay LF
        gitignore = self.root / ".gitignore"
        gitignore.write_bytes(b"node_modules/\n.aos/native/")
        sync_all_instructions(self.root)
        self.assertEqual(
            gitignore.read_bytes(), b"node_modules/\n.aos/native/\n.aos/.backups/\n.playwright-cli/\n"
        )
        sync_all_instructions(self.root)
        self.assertEqual(
            gitignore.read_bytes(), b"node_modules/\n.aos/native/\n.aos/.backups/\n.playwright-cli/\n"
        )

    def test_fresh_manifest_is_up_to_date(self):
        self.write_manifest(native_source_hash(self.root))
        self.assertEqual(native_status(self.root), {"claude-code": "al día"})

    def test_role_change_makes_manifest_stale(self):
        self.write_manifest(native_source_hash(self.root))
        local = self.root / AOS_DIR_NAME / "agents" / "reviewer.local.md"
        local.write_text("- Revisar también los contratos de eventos.\n", encoding="utf-8")
        self.assertIn("DESACTUALIZADO", native_status(self.root)["claude-code"])
        self.assertIn("DESACTUALIZADO", sync_all_instructions(self.root)[".aos/native/claude-code.json"])

    def test_stale_message_points_to_command_or_skill(self):
        self.write_manifest("viejo")
        (self.native / "cursor.json").write_text("{}", encoding="utf-8")
        status = native_status(self.root)
        self.assertIn("aos adapt-native claude-code", status["claude-code"])
        self.assertIn("skill adapt-native", status["cursor"])

    def test_skill_starting_to_apply_makes_manifest_stale(self):
        self.write_manifest(native_source_hash(self.root))
        (self.root / "migrations").mkdir()
        self.assertIn("DESACTUALIZADO", native_status(self.root)["claude-code"])

    def test_corrupt_manifest_is_stale_not_crash(self):
        (self.native / "cursor.json").write_text("{no json", encoding="utf-8")
        self.assertIn("DESACTUALIZADO", native_status(self.root)["cursor"])


class FakeAdapter(NativeAdapter):
    TOOL = "fake"

    def agents(self, roles):
        return {f".fake/agents/{r.name}.md": f"{self.marker(r.name)}\n{r.description}\n" for r in roles}

    def skills(self, skills):
        return {f".fake/skills/{s.name}/SKILL.md": self.skill_md(s) for s in skills}

    def hooks(self):
        return [JsonMerge(".fake/settings.json", ["hooks", "start"], [{"cmd": "dass_aos refresh"}], "hooks.start",
                          owns=lambda item: "dass_aos" in json.dumps(item))]


class TestNativeAdapterBase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / ".git").mkdir()
        init_project(self.root, project_name="demo", tools=["claude-code", "antigravity"])

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_fake(self, **kw):
        return FakeAdapter(self.root).run(**kw)

    def test_second_run_is_idempotent_and_manifest_up_to_date(self):
        self.assertTrue(self.run_fake(yes=True))
        self.assertEqual(self.run_fake(yes=True), [])
        self.assertEqual(native_status(self.root)["fake"], "al día")

    def test_dry_run_writes_nothing(self):
        before = (self.root / ".gitignore").read_bytes()
        self.assertTrue(self.run_fake(dry_run=True, yes=True))
        self.assertFalse((self.root / ".fake").exists())
        self.assertFalse((self.root / AOS_DIR_NAME / "native" / "fake.json").exists())
        self.assertEqual((self.root / ".gitignore").read_bytes(), before)

    def test_file_without_marker_is_never_touched(self):
        own = self.root / ".fake" / "agents" / "reviewer.md"
        own.parent.mkdir(parents=True)
        own.write_text("mío\n", encoding="utf-8")
        adapter = FakeAdapter(self.root)
        adapter.run(yes=True)
        self.assertEqual(own.read_text(encoding="utf-8"), "mío\n")
        self.assertTrue(any("reviewer.md" in w for w in adapter.warnings))
        self.assertNotIn(".fake/agents/reviewer.md", (self.root / ".gitignore").read_text(encoding="utf-8"))

    def test_stale_generated_file_is_deleted(self):
        custom = self.root / AOS_DIR_NAME / "agents" / "custom.md"
        custom.write_text('---\ndescription: "x"\ntools_allowed: ["read"]\n---\n', encoding="utf-8")
        self.run_fake(yes=True)
        self.assertTrue((self.root / ".fake" / "agents" / "custom.md").exists())
        custom.unlink()
        self.assertIn("borrado: .fake/agents/custom.md", self.run_fake(yes=True))
        self.assertFalse((self.root / ".fake" / "agents" / "custom.md").exists())

    def test_keeps_other_tools_gitignore_block(self):
        gi = self.root / ".gitignore"
        other = "# >>> DASS-AOS adapt-native: other (generado, no editar) >>>\n.other/x\n# <<< DASS-AOS adapt-native: other <<<\n"
        gi.write_text(gi.read_text(encoding="utf-8") + other, encoding="utf-8")
        self.run_fake(yes=True)
        text = gi.read_text(encoding="utf-8")
        self.assertIn(other, text)
        self.assertIn("# >>> DASS-AOS adapt-native: fake", text)

    def test_sensitive_merge_needs_yes_and_keeps_foreign_items(self):
        settings = self.root / ".fake" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"theme": "dark", "hooks": {"start": [{"cmd": "mine"}]}}), encoding="utf-8")
        adapter = FakeAdapter(self.root)
        adapter.run()
        self.assertEqual(json.loads(settings.read_text(encoding="utf-8"))["hooks"]["start"], [{"cmd": "mine"}])
        self.assertTrue(any("PENDIENTE" in w for w in adapter.warnings))
        self.run_fake(yes=True)
        self.run_fake(yes=True)
        data = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(data["theme"], "dark")
        self.assertEqual(data["hooks"]["start"], [{"cmd": "mine"}, {"cmd": "dass_aos refresh"}])

    def write_old_manifest(self, files_list):
        native = self.root / AOS_DIR_NAME / "native"
        native.mkdir(exist_ok=True)
        (native / "fake.json").write_text(json.dumps({"files": files_list}), encoding="utf-8")

    def test_old_manifest_never_deletes_outside_project_or_unmarked(self):
        outside = self.root.parent / f"{self.root.name}-victim.md"
        outside.write_text("<!-- DASS-AOS-GENERATED -->\n", encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)
        settings = self.root / ".fake" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text('{"permissions": {"deny": ["Read(./.env)"]}}', encoding="utf-8")
        self.write_old_manifest([f"../{outside.name}", str(outside), ".fake/settings.json"])
        changes = self.run_fake()
        self.assertTrue(outside.exists())
        self.assertIn("deny", settings.read_text(encoding="utf-8"))
        self.assertFalse([c for c in changes if c.startswith("borrado")])

    def test_old_manifest_other_spelling_keeps_fresh_file(self):
        self.write_old_manifest([".fake\\agents\\reviewer.md", "./.fake/agents/architect.md"])
        self.run_fake(yes=True)
        self.assertTrue((self.root / ".fake" / "agents" / "reviewer.md").exists())
        self.assertTrue((self.root / ".fake" / "agents" / "architect.md").exists())

    def test_gitignore_start_marker_without_end_is_left_alone(self):
        gi = self.root / ".gitignore"
        broken = "# >>> DASS-AOS adapt-native: fake (generado, no editar) >>>\n.fake/x\n.env\n"
        gi.write_text(broken, encoding="utf-8")
        adapter = FakeAdapter(self.root)
        adapter.run(yes=True)
        adapter.run(yes=True)
        self.assertEqual(gi.read_text(encoding="utf-8"), broken)
        self.assertTrue(any("sin cierre" in w for w in adapter.warnings))

    def test_role_with_bom_and_block_yaml(self):
        role = self.root / AOS_DIR_NAME / "agents" / "custom.md"
        role.write_bytes("﻿---\ndescription: \"x\"\ntools_allowed: [\"read\"]\n---".encode("utf-8"))
        self.run_fake()
        self.assertIn("x", (self.root / ".fake" / "agents" / "custom.md").read_text(encoding="utf-8"))
        role.write_text('---\ndescription: "x"\ntools_allowed:\n  - read\n---\n', encoding="utf-8")
        with self.assertRaises(ValueError):  # loud, never a role silently stripped of every tool
            self.run_fake()

    def test_unknown_tool_lists_supported_and_points_to_skill(self):
        with self.assertRaises(ValueError) as ctx:
            get_adapter("cursor", self.root)
        self.assertIn("claude-code", str(ctx.exception))
        self.assertIn("adapt-native", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
