"""Tests for the interactive Textual TUI (`aos tui`) using Textual Pilot."""
from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from dass_aos.bootstrap import init_project

try:
    import textual  # noqa: F401
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False


@unittest.skipUnless(TEXTUAL_AVAILABLE, "optional `[tui]` dependency (textual) not installed")
class TestAosTui(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.project_root = self.temp_dir / "repo"
        self.project_root.mkdir()
        init_project(self.project_root, project_name="tui-demo", tools=["antigravity"])
        for p in (self.project_root / ".aos" / "plans" / "active").glob("*.md"):
            p.unlink()
        (self.project_root / ".aos" / "plans" / "active" / "001-demo.md").write_text(
            "# Plan: Feature — TUI Pilot\n\n"
            "- [x] Fase 1: Discovery\n"
            "- [ ] Fase 2: Implementación\n",
            encoding="utf-8",
        )
        (self.project_root / ".aos" / "knowledge" / "gotchas" / "demo-gotcha.md").write_text(
            "---\ntitle: Demo TUI Gotcha\nseverity: high\nstatus: abierta\n---\n\n# Demo\n",
            encoding="utf-8",
        )

        # Simulate an Antigravity session + background task
        self.claude_home = self.temp_dir / "claude_home"
        self.agy_home = self.temp_dir / "agy_home"
        self.claude_home.mkdir()
        conv_dir = self.agy_home / "brain" / "conv-pilot" / ".system_generated"
        (conv_dir / "logs").mkdir(parents=True)
        (conv_dir / "tasks").mkdir(parents=True)
        seen = self.project_root / ".aos" / "native" / "antigravity-seen.txt"
        seen.parent.mkdir(parents=True, exist_ok=True)
        seen.write_text("conv-pilot\n", encoding="utf-8")
        (conv_dir / "logs" / "transcript.jsonl").write_text(
            json.dumps({
                "step_index": 0,
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": "2026-11-16T10:50:00Z",
                "input_tokens": 1200,
                "cache_read_tokens": 8000,
                "output_tokens": 350,
                "tool_calls": [{"name": "edit_file", "arguments": {"Path": "app.py"}}],
            }) + "\n",
            encoding="utf-8",
        )
        (conv_dir / "tasks" / "task-1.log").write_text("Running checks...\nOK\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_tui_mounts_renders_telemetry_switches_tabs_and_searches_rag(self):
        from textual.widgets import DataTable, Input, TabbedContent

        from dass_aos.tui.app import AosTuiApp

        async def _exercise():
            app = AosTuiApp(
                project_root=self.project_root,
                interval=10.0,
                claude_home=self.claude_home,
                antigravity_home=self.agy_home,
            )
            async with app.run_test(size=(130, 40)) as pilot:
                for _ in range(40):
                    await pilot.pause(0.15)
                    if app.snapshot is not None:
                        break
                self.assertIsNotNone(app.snapshot)
                self.assertEqual(app.snapshot.status_report.state, "Working")

                phases_table = app.query_one("#dash-phases-table", DataTable)
                self.assertEqual(phases_table.row_count, 2)

                tabs = app.query_one("#main-tabs", TabbedContent)
                await pilot.press("2")
                self.assertEqual(tabs.active, "tab-plans")
                plans_table = app.query_one("#plans-table", DataTable)
                if plans_table.row_count >= 2:
                    initial_doc = app._selected_doc_key
                    plans_table.focus()
                    await pilot.press("down")
                    await pilot.pause(0.15)
                    self.assertNotEqual(app._selected_doc_key, initial_doc)
                    # Applying the same snapshot must preserve cursor row & doc selection
                    selected_before = app._selected_doc_key
                    cursor_before = plans_table.cursor_row
                    app._apply_snapshot(app.snapshot)
                    self.assertEqual(app._selected_doc_key, selected_before)
                    self.assertEqual(plans_table.cursor_row, cursor_before)

                await pilot.press("3")
                self.assertEqual(tabs.active, "tab-agents")
                sess_table = app.query_one("#agents-sessions-table", DataTable)
                self.assertEqual(sess_table.row_count, 1)
                tasks_table = app.query_one("#agents-tasks-table", DataTable)
                self.assertEqual(tasks_table.row_count, 1)

                await pilot.press("4")
                self.assertEqual(tabs.active, "tab-git")

                await pilot.press("5")
                self.assertEqual(tabs.active, "tab-knowledge")
                rag_input = app.query_one("#rag-input", Input)
                rag_input.value = "Gotcha"
                await rag_input.action_submit()
                rag_table = app.query_one("#rag-results-table", DataTable)
                for _ in range(30):
                    await pilot.pause(0.15)
                    if rag_table.row_count >= 1:
                        break
                self.assertGreaterEqual(rag_table.row_count, 1)

                await pilot.press("6")
                self.assertEqual(tabs.active, "tab-console")

                await pilot.press("7")
                self.assertEqual(tabs.active, "tab-tokens")
                self.assertGreaterEqual(app.query_one("#tokens-cat-table", DataTable).row_count, 1)
                self.assertGreaterEqual(app.query_one("#tokens-tools-table", DataTable).row_count, 1)
                self.assertGreaterEqual(app.query_one("#tokens-sessions-table", DataTable).row_count, 1)
                self.assertGreaterEqual(app.query_one("#tokens-harness-table", DataTable).row_count, 1)
                await pilot.press("z")
                await pilot.pause(0.15)
                self.assertEqual(app.screen.__class__.__name__, "ZoomScreen")
                await pilot.press("escape")
                await pilot.pause(0.15)

                # Gonzo-inspired controls: Space pause, ? help modal, z zoom modal, t theme cycle
                await pilot.press("1")
                await pilot.press("space")
                self.assertTrue(app._paused)
                await pilot.press("space")
                self.assertFalse(app._paused)

                await pilot.press("question_mark")
                await pilot.pause(0.15)
                self.assertEqual(app.screen.__class__.__name__, "HelpScreen")
                # Background snapshot refresh while modal is stacked must not raise NoMatches
                app._apply_snapshot(app.snapshot)
                await pilot.press("escape")
                await pilot.pause(0.15)

                await pilot.press("z")
                await pilot.pause(0.15)
                self.assertEqual(app.screen.__class__.__name__, "ZoomScreen")
                await pilot.press("escape")
                await pilot.pause(0.15)

                await pilot.press("t")
                self.assertIn("theme-emerald", app.screen.classes)

        asyncio.run(_exercise())

    def test_tui_runner_executes_doctor_command_non_blocking(self):
        from textual.widgets import Static, TabbedContent

        from dass_aos.tui.app import AosTuiApp

        async def _exercise():
            app = AosTuiApp(
                project_root=self.project_root,
                interval=10.0,
                claude_home=self.claude_home,
                antigravity_home=self.agy_home,
            )
            async with app.run_test(size=(130, 40)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("6")
                await pilot.click("#btn-doctor")
                # Wait for subprocess worker to complete
                for _ in range(30):
                    await pilot.pause(0.2)
                    if not app._runner_busy and app._runner_jobs:
                        break
                tabs = app.query_one("#main-tabs", TabbedContent)
                self.assertEqual(tabs.active, "tab-console")
                self.assertTrue(app._runner_jobs)
                self.assertEqual(app._runner_jobs[0].status, "finished")
                status_text = str(app.query_one("#runner-status-bar", Static).render())
                self.assertIn("PASSED", status_text)

        asyncio.run(_exercise())


@unittest.skipUnless(TEXTUAL_AVAILABLE, "optional `[tui]` dependency (textual) not installed")
class TestTuiFormatters(unittest.TestCase):
    def test_markdown_diff_keeps_tables_renderable(self):
        from dass_aos.tui.widgets import markdown_diff

        doc = "# T\n\n| A | B |\n|---|---|\n| 1 | x |\n| 2 | y |\n| 3 | z |\n"
        diff = "@@ -6,1 +6,1 @@\n-| 2 | old |\n+| 2 | y |\n"
        md = markdown_diff(diff, doc)
        assert "| A | B |\n|---|---|" in md  # header injected for a mid-table hunk
        assert "| **+** 2 | y |" in md
        assert "~~old~~" in md


    def test_format_output_line_colors_plain_output_and_keeps_ansi(self):
        from dass_aos.tui.widgets import format_output_line

        passed = format_output_line("  ✓ PASSED   LINT   exitoso")
        assert any("#34d399" in str(s.style) for s in passed.spans)
        failed = format_output_line("  ✗ FAILED   TEST")
        assert any("#c46a6a" in str(s.style) for s in failed.spans)
        ansi = format_output_line("\x1b[31mred\x1b[0m")
        assert ansi.plain == "red" and all("#" not in str(s.style) for s in ansi.spans)
