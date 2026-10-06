"""Tests for adapt-native manifests and staleness detection (ADR-004)."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from dass_aos.bootstrap import init_project
from dass_aos.constants import AOS_DIR_NAME
from dass_aos.sync import native_source_hash, native_status, sync_all_instructions


class TestNative(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / ".git").mkdir()
        init_project(self.root, project_name="demo")
        self.native = self.root / AOS_DIR_NAME / "native"
        self.native.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write_manifest(self, source_hash):
        (self.native / "claude-code.json").write_text(json.dumps({"source_hash": source_hash}), encoding="utf-8")

    def test_init_ignores_native_dir_once(self):
        init_project(self.root, project_name="demo")
        self.assertEqual((self.root / ".gitignore").read_text(encoding="utf-8").count(".aos/native/"), 1)

    def test_fresh_manifest_is_up_to_date(self):
        self.write_manifest(native_source_hash(self.root))
        self.assertEqual(native_status(self.root), {"claude-code": "al día"})

    def test_role_change_makes_manifest_stale(self):
        self.write_manifest(native_source_hash(self.root))
        local = self.root / AOS_DIR_NAME / "agents" / "reviewer.local.md"
        local.write_text("- Revisar también los contratos de eventos.\n", encoding="utf-8")
        self.assertIn("DESACTUALIZADO", native_status(self.root)["claude-code"])
        self.assertIn("DESACTUALIZADO", sync_all_instructions(self.root)[".aos/native/claude-code.json"])

    def test_skill_starting_to_apply_makes_manifest_stale(self):
        self.write_manifest(native_source_hash(self.root))
        (self.root / "migrations").mkdir()
        self.assertIn("DESACTUALIZADO", native_status(self.root)["claude-code"])

    def test_corrupt_manifest_is_stale_not_crash(self):
        (self.native / "cursor.json").write_text("{no json", encoding="utf-8")
        self.assertIn("DESACTUALIZADO", native_status(self.root)["cursor"])


if __name__ == "__main__":
    unittest.main()
