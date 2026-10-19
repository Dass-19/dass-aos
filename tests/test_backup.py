"""Tests for the pre-write snapshots (ADR-008 safety net)."""
import shutil
import tempfile
import unittest
from pathlib import Path

from dass_aos.backup import MAX_SNAPSHOTS, Snapshots
from dass_aos.bootstrap import init_project
from dass_aos.sync import sync_all_instructions


class TestSnapshots(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        (self.temp_dir / ".aos").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_snapshot_copies_and_is_idempotent(self):
        target = self.temp_dir / "CLAUDE.md"
        target.write_text("v1", encoding="utf-8")
        snapshots = Snapshots(self.temp_dir)
        snapshots.snapshot(target)
        target.write_text("v2", encoding="utf-8")
        snapshots.snapshot(target)  # must not overwrite the first copy
        copies = list(snapshots.directory.rglob("CLAUDE.md"))
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0].read_text(encoding="utf-8"), "v1")

    def test_missing_file_is_ignored(self):
        snapshots = Snapshots(self.temp_dir)
        snapshots.snapshot(self.temp_dir / "nope.md")
        self.assertFalse(snapshots.directory.exists())

    def test_disabled_snapshots_write_nothing(self):
        target = self.temp_dir / "x.md"
        target.write_text("v1", encoding="utf-8")
        Snapshots(self.temp_dir, enabled=False).snapshot(target)
        self.assertFalse((self.temp_dir / ".aos" / ".backups").exists())

    def test_old_snapshots_are_pruned(self):
        base = self.temp_dir / ".aos" / ".backups"
        for i in range(MAX_SNAPSHOTS + 3):
            (base / f"20260101-0000{i:02d}").mkdir(parents=True)
        target = self.temp_dir / "y.md"
        target.write_text("v1", encoding="utf-8")
        Snapshots(self.temp_dir).snapshot(target)
        self.assertEqual(len([p for p in base.iterdir() if p.is_dir()]), MAX_SNAPSHOTS)

    def test_sync_snapshots_the_file_it_overwrites(self):
        init_project(self.temp_dir, project_name="demo", tools=["claude-code"])
        # A new project skill changes the always-on block, so CLAUDE.md is rendered again.
        skill = self.temp_dir / ".aos" / "skills" / "specs" / "mia.md"
        skill.write_text(
            '---\nname: "mia"\ndescription: "skill del proyecto"\ncost: on-demand\n---\n\n# Skill: mia\n',
            encoding="utf-8",
        )
        sync_all_instructions(self.temp_dir)
        copies = list((self.temp_dir / ".aos" / ".backups").rglob("CLAUDE.md"))
        self.assertEqual(len(copies), 1)
        self.assertIn("DASS-AOS", copies[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
