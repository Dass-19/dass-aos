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

    def test_tui_lazy_tabs_herdr_session_controls_mute_and_voice(self):
        from textual.widgets import DataTable, Input, TabbedContent

        from dass_aos.tui.app import AosTuiApp

        async def _exercise():
            app = AosTuiApp(
                project_root=self.project_root,
                interval=10.0,
                claude_home=self.claude_home,
                antigravity_home=self.agy_home,
            )
            async with app.run_test(size=(130, 42)) as pilot:
                for _ in range(40):
                    await pilot.pause(0.15)
                    if app.snapshot is not None:
                        break
                self.assertIsNotNone(app.snapshot)

                # CA-1: While on tab-overview, inactive tabs are marked dirty until visited
                self.assertIn("tab-tokens", app._dirty_tabs)
                await pilot.press("3")
                tabs = app.query_one("#main-tabs", TabbedContent)
                self.assertEqual(tabs.active, "tab-agents")
                self.assertNotIn("tab-agents", app._dirty_tabs)

                # CA-4: Toggle mute with `m`
                self.assertFalse(app.alerts.muted)
                await pilot.press("m")
                self.assertTrue(app.alerts.muted)

                # CA-5: Create a new named Herdr-style session via `#btn-agent-new` / action
                sess_table = app.query_one("#agents-sessions-table", DataTable)
                before_rows = sess_table.row_count
                app.action_new_agent_session()
                await pilot.pause(0.15)
                self.assertEqual(sess_table.row_count, before_rows + 1)

                # CA-6: Toggle voice mode on selected session
                selected_key = app._selected_session_key
                self.assertIsNotNone(selected_key)
                app.action_toggle_voice_mode()
                self.assertTrue(app.controller.is_voice_enabled(selected_key))

                # CA-5: Prompt input exists in Tab 3
                prompt_input = app.query_one("#agent-prompt-input", Input)
                self.assertIsNotNone(prompt_input)

                # CA-7: Live embedded PTY terminal widget exists in Tab 3 and supports Terminal Mode + View toggle
                from dass_aos.tui.pty_terminal import AgentTerminalWidget

                # Enrich selected session with multi-line metadata to verify terminal viewport does not collapse (H1)
                sel_sess = app._sessions_by_key[app._selected_session_key]
                sel_sess.workflows = ["Workflow: coordinar.js", "Skill: phased-delivery", "Skill: adversarial-review"]
                sel_sess.subagents = ["R1 Risk", "R2 Resilience", "R3 UX", "R4 Reliability"]
                sel_sess.touched_files = ["dass_aos/telemetry.py", "dass_aos/tui/app.py", "dass_aos/tui/pty_terminal.py"]
                sel_sess.recent_tools = ["read_file", "edit_file", "run_command", "invoke_subagent"]
                app._last_session_sig = None
                app._render_selected_session()
                await pilot.pause(0.15)

                term_widget = app.query_one("#agent-terminal-pane", AgentTerminalWidget)
                self.assertIsNotNone(term_widget)
                self.assertGreaterEqual(term_widget.size.height, 12)

                # Focusing terminal widget must capture keys (v, q, 1, space) without leaking to App.BINDINGS (H3)
                term_widget.focus()
                await pilot.pause(0.05)
                await pilot.press("v", "1", "space")
                await pilot.pause(0.05)
                self.assertEqual(tabs.active, "tab-agents")
                self.assertFalse(app._paused)
                await pilot.press("ctrl+g")
                await pilot.pause(0.05)

                # Toggle between Terminal PTY view, Subagent Graph view (`g`), and Inspector view
                await pilot.press("g")
                await pilot.pause(0.1)
                self.assertEqual(app._agent_right_mode, "graph")
                self.assertIn("Grafo de Subagentes", str(app.query_one("#agents-activity-box").border_title))
                app.action_toggle_agent_view()
                await pilot.pause(0.1)
                self.assertEqual(app._agent_right_mode, "inspector")
                app.action_toggle_agent_view()
                await pilot.pause(0.1)
                self.assertEqual(app._agent_right_mode, "terminal")

        asyncio.run(_exercise())

    def test_zoom_screen_does_not_ping_pong_pty_resize_on_tick(self):
        from unittest import mock

        from dass_aos.tui.app import AosTuiApp, ZoomScreen
        from dass_aos.tui.pty_terminal import AgentTerminalWidget, PtySession

        async def _exercise():
            app = AosTuiApp(
                project_root=self.project_root,
                interval=10.0,
                claude_home=self.claude_home,
                antigravity_home=self.agy_home,
            )
            async with app.run_test(size=(130, 36)) as pilot:
                for _ in range(40):
                    await pilot.pause(0.1)
                    if app.snapshot is not None:
                        break
                await pilot.press("3")
                await pilot.pause(0.15)
                skey = app._selected_session_key
                fake_pty = PtySession(skey, ["cmd"], self.project_root, cols=66, rows=12)
                fake_pty.alive = True
                app.controller.pty_sessions[skey] = fake_pty
                term = app.query_one("#agent-terminal-pane", AgentTerminalWidget)
                term.attach_pty(fake_pty)
                await pilot.pause(0.1)

                sizes_seen = []
                orig_resize = fake_pty.resize

                def _spy_resize(cols: int, rows: int) -> None:
                    sizes_seen.append((cols, rows))
                    orig_resize(cols, rows)

                with mock.patch.object(fake_pty, "resize", side_effect=_spy_resize):
                    await pilot.press("z")
                    await pilot.pause(0.35)
                    self.assertIsInstance(app.screen, ZoomScreen)
                    sizes_seen.clear()
                    # Simulate _tick_pty firing while output arrives in ZoomScreen
                    fake_pty.screen.feed("nueva salida\r\n")
                    with mock.patch.object(app.controller, "poll_all_ptys", return_value=True):
                        app._tick_pty()
                        await pilot.pause(0.1)
                    # Hidden #agent-terminal-pane must NOT shrink PTY below Zoom width while zoomed
                    for c, _r in sizes_seen:
                        self.assertGreaterEqual(c, 95)

        asyncio.run(_exercise())

    def test_clean_pty_exit_closes_terminal_and_returns_focus(self):
        import sys

        from dass_aos.tui.app import AosTuiApp, ZoomScreen
        from dass_aos.tui.pty_terminal import AgentTerminalWidget

        async def _exercise():
            app = AosTuiApp(
                project_root=self.project_root,
                interval=10.0,
                claude_home=self.claude_home,
                antigravity_home=self.agy_home,
            )
            async with app.run_test(size=(130, 36)) as pilot:
                for _ in range(40):
                    await pilot.pause(0.1)
                    if app.snapshot is not None:
                        break
                await pilot.press("3")
                await pilot.pause(0.15)
                skey = app._selected_session_key
                sess = app._sessions_by_key[skey]
                term = app.query_one("#agent-terminal-pane", AgentTerminalWidget)

                # Launch a real short interactive process that exits with code 0 on `/exit`
                pty_s = app.controller.open_or_attach_pty(
                    sess,
                    cols=70,
                    rows=18,
                    command_override=[
                        sys.executable,
                        "-u",
                        "-c",
                        "import sys; print('READY', flush=True); line = sys.stdin.readline().strip(); print('BYE:' + line, flush=True)",
                    ],
                )
                term.attach_pty(pty_s)
                term.focus()
                await pilot.press("ctrl+g")
                await pilot.pause(0.05)
                await pilot.press("z")
                await pilot.pause(0.2)
                self.assertIsInstance(app.screen, ZoomScreen)

                # Simulate user typing `/exit` + Enter inside Zoom terminal -> process exits with code 0
                pty_s.write("/exit\r\n")
                for _ in range(30):
                    await pilot.pause(0.1)
                    if skey not in app.controller.pty_sessions and not isinstance(app.screen, ZoomScreen):
                        break

                self.assertNotIn(skey, app.controller.pty_sessions)
                self.assertIsNone(term.pty_session)
                self.assertNotIsInstance(app.screen, ZoomScreen)
                self.assertNotIsInstance(app.focused, AgentTerminalWidget)

        asyncio.run(_exercise())

    def test_agents_tab_filters_tasks_by_session_and_switches_views_and_voice_state(self):
        from textual.widgets import Button, DataTable

        from dass_aos.telemetry import AgentTaskInfo
        from dass_aos.tui.app import AosTuiApp

        async def _exercise():
            app = AosTuiApp(
                project_root=self.project_root,
                interval=10.0,
                claude_home=self.claude_home,
                antigravity_home=self.agy_home,
            )
            async with app.run_test(size=(130, 42)) as pilot:
                for _ in range(40):
                    await pilot.pause(0.1)
                    if app.snapshot is not None:
                        break
                await pilot.press("3")
                await pilot.pause(0.15)

                skey = app._selected_session_key
                sess = app._sessions_by_key[skey]
                t_mine = AgentTaskInfo(
                    id="t-mine",
                    agent=sess.tool,
                    status="finished",
                    title="My Session Task",
                    session_id=sess.session_id,
                    started_at=1700000000.0,
                    updated_at=1700000030.0,
                    tail_lines=["done mine"],
                )
                t_other = AgentTaskInfo(
                    id="t-other",
                    agent="claude-code",
                    status="finished",
                    title="Other Session Task",
                    session_id="other-session-id-999",
                    started_at=1700000000.0,
                    updated_at=1700000020.0,
                    tail_lines=["done other"],
                )
                app._all_tasks = [t_mine, t_other]
                app._sync_tasks_table()
                await pilot.pause(0.1)

                # Default filter is by selected session
                self.assertEqual(app._tasks_filter_mode, "session")
                self.assertEqual(len(app._tasks_by_key), 1)
                self.assertIn("t-mine", next(iter(app._tasks_by_key)))

                # Switching filter to "all" shows both tasks
                app._set_tasks_filter("all")
                await pilot.pause(0.05)
                self.assertEqual(len(app._tasks_by_key), 2)
                self.assertTrue(app.query_one("#btn-tasks-filter-all", Button).has_class("-active"))

                # Switching back to "session" filters again
                app._set_tasks_filter("session")
                await pilot.pause(0.05)
                self.assertEqual(len(app._tasks_by_key), 1)

                # View pills switch cleanly including Log view showing #agents-log-box
                app._set_agent_right_mode("log")
                await pilot.pause(0.05)
                self.assertTrue(app.query_one("#agents-log-box").display)
                self.assertFalse(app.query_one("#agents-activity-box").display)
                self.assertTrue(app.query_one("#btn-view-log", Button).has_class("-active"))

                # Voice button remains present and highlights when voice mode is toggled on
                btn_voice = app.query_one("#btn-agent-voice", Button)
                self.assertFalse(btn_voice.has_class("-voice-on"))
                app.action_toggle_voice_mode()
                await pilot.pause(0.05)
                self.assertTrue(btn_voice.has_class("-voice-on"))
                self.assertEqual(app.query_one("#agents-tasks-table", DataTable).row_count, 1)

        asyncio.run(_exercise())

    def test_attach_pty_validates_cli_installation_and_opens_install_modal_when_missing(self):
        from unittest import mock

        from dass_aos.tui.app import AosTuiApp, CliInstallScreen

        async def _exercise():
            app = AosTuiApp(
                project_root=self.project_root,
                interval=10.0,
                claude_home=self.claude_home,
                antigravity_home=self.agy_home,
            )
            async with app.run_test(size=(130, 40)) as pilot:
                for _ in range(40):
                    await pilot.pause(0.1)
                    if app.snapshot is not None:
                        break
                await pilot.press("3")
                await pilot.pause(0.15)
                with mock.patch("shutil.which", return_value=None):
                    info_ag = app.controller.check_cli_availability("antigravity")
                    self.assertFalse(info_ag["installed"])
                    self.assertIn("antigravity.google/cli/install", info_ag["install_display"])
                    self.assertIn("inicia sesión", info_ag["login_hint"].lower())

                    info_cc = app.controller.check_cli_availability("claude-code")
                    self.assertFalse(info_cc["installed"])
                    self.assertIn("claude.ai/install", info_cc["install_display"])

                    app.action_attach_agent_pty()
                    await pilot.pause(0.1)
                    self.assertIsInstance(app.screen, CliInstallScreen)
                    await pilot.press("escape")
                    await pilot.pause(0.05)
                    self.assertNotIsInstance(app.screen, CliInstallScreen)

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

    def test_format_diff_lines_renders_gutter_inline_highlights_and_stats(self):
        from dass_aos.tui.widgets import diff_stats, format_diff_lines, format_git_commit_line

        sample = (
            "diff --git a/.aos/config.json b/.aos/config.json\n"
            "index 15f1228..85e3403 100644\n"
            "--- a/.aos/config.json\n"
            "+++ b/.aos/config.json\n"
            "@@ -1,4 +1,4 @@\n"
            " {\n"
            '-  "aos_version": "0.8.0",\n'
            '+  "aos_version": "0.9.0",\n'
            '   "client_generator": "generic"\n'
        )
        self.assertEqual(diff_stats(sample), (1, 1, 1))
        rendered = list(format_diff_lines(sample))
        plains = [r.plain for r in rendered]
        # Boilerplate headers stripped; clean hunk header and dual line numbers shown
        self.assertFalse(any("diff --git" in p for p in plains))
        self.assertTrue(any("Línea 1" in p for p in plains))
        del_line = next(r for r in rendered if "0.8.0" in r.plain)
        add_line = next(r for r in rendered if "0.9.0" in r.plain)
        self.assertIn("2", del_line.plain)
        self.assertIn("2", add_line.plain)
        # Intra-line highlight span present on the changed character ("8" -> "9")
        self.assertTrue(any("#5c1d24" in str(sp.style) for sp in del_line.spans))
        self.assertTrue(any("#14533c" in str(sp.style) for sp in add_line.spans))

        commit = format_git_commit_line("f11c441 feat(tui): add PTY")
        self.assertIn("f11c441", commit.plain)
        self.assertTrue(any("#d9b15f" in str(sp.style) for sp in commit.spans))


    def test_format_output_line_colors_plain_output_and_keeps_ansi(self):
        from dass_aos.tui.widgets import format_output_line

        passed = format_output_line("  ✓ PASSED   LINT   exitoso")
        assert any("#34d399" in str(s.style) for s in passed.spans)
        failed = format_output_line("  ✗ FAILED   TEST")
        assert any("#c46a6a" in str(s.style) for s in failed.spans)
        ansi = format_output_line("\x1b[31mred\x1b[0m")
        assert ansi.plain == "red" and all("#" not in str(s.style) for s in ansi.spans)

    def test_format_task_datetime_and_enriched_session_summary(self):
        from dass_aos.telemetry import AgentSessionInfo, AgentTaskInfo
        from dass_aos.tui.widgets import (
            format_session_detail_summary,
            format_task_datetime,
            format_task_log_header,
        )

        # 2026-11-18 10:00:00 local-independent check
        task = AgentTaskInfo(
            id="task-42",
            agent="claude-code",
            status="finished",
            title="Audit security",
            started_at=1795000000.0,
            updated_at=1795000045.0,
            kind="subagent",
        )
        dt_str = format_task_datetime(task.started_at, task.updated_at)
        self.assertRegex(dt_str, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
        self.assertIn("45s", dt_str)

        hdr = format_task_log_header(task)
        self.assertIn("task-42", hdr)
        self.assertIn("→", hdr)
        self.assertIn("45s", hdr)

        sess = AgentSessionInfo(
            tool="claude-code",
            session_id="sess-99",
            title="Refactor Auth",
            status="pending",
            pending_reason="Pregunta: ¿Aprobamos migración?",
            subagents=["reviewer: security"],
            workflows=["Workflow: deploy.js", "Skill: phased-delivery"],
            touched_files=["dass_aos/telemetry.py", "dass_aos/tui/app.py"],
            voice_active=True,
        )
        summary = format_session_detail_summary(sess).plain
        self.assertIn("PENDING", summary.upper())
        self.assertIn("¿Aprobamos migración?", summary)
        self.assertIn("deploy.js", summary)
        self.assertIn("dass_aos/telemetry.py", summary)
        self.assertIn("VOZ", summary.upper())


class TestTuiControllerAndAlerts(unittest.TestCase):
    def test_clean_speech_text_strips_code_blocks_and_diffs_for_tts(self):
        from dass_aos.tui.controller import clean_speech_text

        raw = (
            "He revisado el módulo.\n"
            "```python\ndef foo():\n    return 42\n```\n"
            "@@ -1,3 +1,3 @@\n-old line\n+new line\n"
            "¿Quieres que aplique el cambio en [app.py](file:///c:/repo/app.py)?"
        )
        cleaned = clean_speech_text(raw)
        self.assertIn("He revisado el módulo.", cleaned)
        self.assertIn("¿Quieres que aplique el cambio en app.py?", cleaned)
        self.assertNotIn("def foo", cleaned)
        self.assertNotIn("@@", cleaned)
        self.assertNotIn("+new line", cleaned)

    def test_alert_dispatcher_fires_once_on_pending_transition_and_respects_mute(self):
        from unittest import mock

        from dass_aos.telemetry import AgentSessionInfo
        from dass_aos.tui.controller import AlertDispatcher

        dispatcher = AlertDispatcher(muted=False)
        s_running = AgentSessionInfo(tool="claude-code", session_id="s1", title="Build", status="running")
        s_pending = AgentSessionInfo(
            tool="claude-code",
            session_id="s1",
            title="Build",
            status="pending",
            pending_reason="Pregunta: ¿Usamos caché?",
        )

        with mock.patch.object(dispatcher, "play_sound") as m_sound, mock.patch.object(
            dispatcher, "send_os_toast"
        ) as m_toast:
            # Running -> no alert
            self.assertEqual(dispatcher.process_sessions([s_running]), [])
            m_sound.assert_not_called()

            # Transition to pending -> fires sound + toast once
            triggered = dispatcher.process_sessions([s_pending])
            self.assertEqual(len(triggered), 1)
            m_sound.assert_called_once()
            m_toast.assert_called_once()

            # Same pending reason on next tick -> no duplicate sound/toast
            self.assertEqual(dispatcher.process_sessions([s_pending]), [])
            self.assertEqual(m_sound.call_count, 1)

            # Mute suppresses sound and OS toast on a new pending session
            dispatcher.muted = True
            s_pending_2 = AgentSessionInfo(
                tool="antigravity",
                session_id="s2",
                title="Audit",
                status="pending",
                pending_reason="Feedback requerido",
            )
            triggered2 = dispatcher.process_sessions([s_pending_2])
            self.assertEqual(len(triggered2), 1)
            self.assertEqual(m_sound.call_count, 1)
            self.assertEqual(m_toast.call_count, 1)

    def test_session_controller_builds_herdr_commands_and_manages_voice_tts(self):
        from unittest import mock

        from dass_aos.telemetry import AgentSessionInfo
        from dass_aos.tui.controller import SessionController, TTSManager

        tts = TTSManager()
        ctrl = SessionController(project_root=Path("."), tts=tts)

        cmd_resume = ctrl.build_prompt_command(
            tool="claude-code",
            prompt="Continúa con la Fase 3",
            session_id="sess-123",
            resume=True,
        )
        self.assertEqual(cmd_resume[:3], ["claude", "--resume", "sess-123"])
        self.assertIn("Continúa con la Fase 3", cmd_resume)
        self.assertIn("stream-json", cmd_resume)

        cmd_new = ctrl.build_prompt_command(
            tool="claude-code",
            prompt="Audita seguridad",
            session_id="sess-new-id",
            session_name="sec-audit",
            resume=False,
        )
        self.assertIn("--session-id", cmd_new)
        self.assertIn("-n", cmd_new)
        self.assertIn("sec-audit", cmd_new)

        # Voice mode synchronization: when session has voice_active and new assistant text arrives, TTS speaks it
        ctrl.enable_voice("claude-code:sess-123")
        sess = AgentSessionInfo(
            tool="claude-code",
            session_id="sess-123",
            title="Voice Sess",
            status="active",
            voice_active=True,
            last_assistant_text="Listo, terminé la revisión. ¿Seguimos?",
        )
        with mock.patch.object(tts, "speak", return_value=True) as m_speak:
            ctrl.sync_voice_sessions([sess])
            m_speak.assert_called_once_with("Listo, terminé la revisión. ¿Seguimos?")
            # Calling again with identical text does not repeat speech
            ctrl.sync_voice_sessions([sess])
            self.assertEqual(m_speak.call_count, 1)

    def test_vt_screen_parses_ansi_truecolor_cursor_and_osc_titles(self):
        from dass_aos.tui.pty_terminal import VtScreen

        scr = VtScreen(cols=60, rows=10)
        scr.feed(
            "\x1b]0;⠋ Claude Code\x1b\\"
            "\x1b[2J\x1b[H\x1b[2 q\x1b[!p\x1b[?2004h"
            "\x1b[1;38;2;217;177;95mClaude Code v2.1\x1b[0m\r\n"
            "Read(dass_aos/tui/app.py)\r\n"
            "\x1b[32m+ linea nueva\x1b[0m"
        )
        self.assertEqual(scr.osc_title, "⠋ Claude Code")
        plain = scr.plain_text()
        self.assertIn("Claude Code v2.1", plain)
        self.assertIn("Read(dass_aos/tui/app.py)", plain)
        self.assertIn("+ linea nueva", plain)
        self.assertNotIn("[2 q", plain)
        self.assertNotIn("[!p", plain)
        rich_txt = scr.render_rich(show_cursor=True)
        self.assertTrue(any("#d9b15f" in str(sp.style).lower() for sp in rich_txt.spans))

    def test_detect_terminal_agent_state_matches_herdr_rules(self):
        from dass_aos.tui.pty_terminal import VtScreen, detect_terminal_agent_state

        scr = VtScreen(cols=70, rows=12)
        # 1. Working via spinner in OSC title or footer
        scr.feed("\x1b]0;⠋ Working\x07\x1b[2J\x1b[H⠋ Reading files… (3s · esc to interrupt)")
        st, reason = detect_terminal_agent_state(scr)
        self.assertEqual(st, "running")

        # 2. Blocked / Pending via Claude permission prompt
        scr.feed(
            "\x1b]0;✳ Claude\x07\x1b[2J\x1b[H"
            "Bash command: rm -rf dist\r\n"
            "Do you want to proceed?\r\n"
            "❯ 1. Yes\r\n"
            "  2. No\r\n"
            "Enter to confirm · Esc to cancel"
        )
        st2, reason2 = detect_terminal_agent_state(scr)
        self.assertEqual(st2, "pending")
        self.assertTrue(reason2)

        # 3. Blocked via Antigravity question footer
        scr.feed("\x1b[2J\x1b[H¿Qué opción prefieres?\r\n↑/↓ Navigate · enter Select · esc Skip")
        st3, reason3 = detect_terminal_agent_state(scr)
        self.assertEqual(st3, "pending")

        # 4. Idle at prompt box
        scr.feed("\x1b[2J\x1b[HDone.\r\n❯ ")
        st4, _ = detect_terminal_agent_state(scr)
        self.assertEqual(st4, "idle")

    def test_pty_process_spawns_reads_and_writes_interactively(self):
        import sys
        import time

        from dass_aos.tui.pty_terminal import PtySession

        cmd = [
            sys.executable,
            "-u",
            "-c",
            "import sys; line = sys.stdin.readline().strip(); print('PTY_ECHO:' + line, flush=True)",
        ]
        pty_sess = PtySession(session_key="test:pty", command=cmd, cwd=Path("."), cols=80, rows=20)
        pty_sess.start()
        try:
            time.sleep(0.2)
            pty_sess.write("HOLA_HERDR\r\n")
            deadline = time.time() + 4.0
            while time.time() < deadline:
                pty_sess.poll_output()
                if "PTY_ECHO:HOLA_HERDR" in pty_sess.screen.plain_text():
                    break
                time.sleep(0.1)
            self.assertIn("PTY_ECHO:HOLA_HERDR", pty_sess.screen.plain_text())
            # Wait briefly for short-lived process to finish and verify alive transitions to False (H4)
            for _ in range(25):
                pty_sess.poll_output()
                if not pty_sess.alive:
                    break
                time.sleep(0.05)
            self.assertFalse(pty_sess.alive)
        finally:
            pty_sess.stop()

    def test_subagent_graph_view_renders_topology_and_interactions(self):
        from dass_aos.telemetry import AgentActivityItem, AgentSessionInfo, AgentTaskInfo
        from dass_aos.tui.widgets import format_subagent_graph

        parent = AgentSessionInfo(
            tool="antigravity",
            session_id="95938c9c-f573-4376-968e-17a4eb18fe97",
            title="ejecuta la revisino adversarial",
            status="active",
            subagents=[
                "R1 Risk Reviewer",
                "R2 Resilience Reviewer",
                "4R Findings Adversarial Verifier",
            ],
            workflows=["Skill:adversarial-review"],
            activities=[
                AgentActivityItem("10:49:10", "antigravity", "tool", "subagent: R1 Risk Reviewer"),
                AgentActivityItem("10:49:12", "antigravity", "tool", "subagent: R2 Resilience Reviewer"),
                AgentActivityItem("10:51:00", "antigravity", "tool", "send_message -> 22fb6c20: Reporta hallazgos"),
                AgentActivityItem("10:54:00", "antigravity", "tool", "subagent: 4R Findings Adversarial Verifier"),
            ],
        )
        tasks = [
            AgentTaskInfo(
                id="sub-r1",
                agent="antigravity",
                status="finished",
                title="reviewer: R1 Risk Reviewer",
                session_id=parent.session_id,
                started_at=1700000000.0,
                updated_at=1700000042.0,
                tail_lines=["[reviewer] R1 Risk Reviewer — CONFIRMADO H2, H5"],
                kind="subagent",
                agent_type="reviewer",
            ),
            AgentTaskInfo(
                id="sub-r2",
                agent="antigravity",
                status="running",
                title="reviewer: R2 Resilience Reviewer",
                session_id=parent.session_id,
                started_at=1700000010.0,
                updated_at=1700000030.0,
                tail_lines=["[reviewer] R2 Resilience Reviewer — Auditando pty_terminal.py"],
                kind="subagent",
                agent_type="reviewer",
            ),
        ]

        graph_txt = format_subagent_graph(parent, all_sessions=[parent], all_tasks=tasks)
        plain = graph_txt.plain
        self.assertIn("COORDINADOR", plain)
        self.assertIn("ejecuta la revisino adversarial", plain)
        self.assertIn("R1 Risk Reviewer", plain)
        self.assertIn("R2 Resilience Reviewer", plain)
        self.assertIn("4R Findings Adversarial Verifier", plain)
        self.assertIn("send_message", plain)
        self.assertIn("──►", plain)

    def test_session_controller_builds_agy_commands_and_detects_agy_tui_states(self):
        import tempfile
        from unittest import mock

        from dass_aos.telemetry import AgentSessionInfo
        from dass_aos.tui.controller import SessionController
        from dass_aos.tui.pty_terminal import VtScreen, detect_terminal_agent_state

        with tempfile.TemporaryDirectory() as td:
            cli_home = Path(td) / "antigravity-cli"
            (cli_home / "conversations").mkdir(parents=True)
            cli_sid = "a1860ee7-4b3f-405f-a104-b97d9476cb98"
            (cli_home / "conversations" / f"{cli_sid}.db").write_bytes(b"")

            ctrl = SessionController(project_root=Path(td), antigravity_cli_home=cli_home)
            with mock.patch("shutil.which", return_value="agy"):
                # 1. Native CLI session -> `agy --conversation <id>`
                s_cli = AgentSessionInfo(
                    tool="antigravity",
                    session_id=cli_sid,
                    title="CLI test",
                    status="idle",
                    cwd=td,
                    meta="1 task(s) · agy-cli",
                )
                self.assertEqual(
                    ctrl.build_interactive_cli_command(s_cli),
                    ["agy", "--conversation", cli_sid],
                )

                # 2. Brand-new session from TUI -> bare `agy`
                s_new = ctrl.create_named_session("agy-fresh", tool="antigravity")
                self.assertEqual(ctrl.build_interactive_cli_command(s_new), ["agy"])

                # 3. IDE-only session -> launches `agy` (and open_or_attach_pty drives `/resume` -> `Other` import)
                s_ide = AgentSessionInfo(
                    tool="antigravity",
                    session_id="44a73571-7925-4d79-81d7-ad6411457dfd",
                    title="En planes del aos",
                    status="idle",
                    cwd=td,
                    meta="1 task(s) · agy-ide",
                    summary_title="Antigravity Native Adaptation Verification",
                )
                self.assertTrue(ctrl.needs_agy_ide_import(s_ide))
                self.assertEqual(ctrl.build_interactive_cli_command(s_ide), ["agy"])

                # 4. Non-interactive prompt command for agy CLI
                pcmd = ctrl.build_prompt_command("antigravity", "hola", session_id=cli_sid, resume=True)
                self.assertEqual(
                    pcmd,
                    ["agy", "--conversation", cli_sid, "-p", "hola", "--output-format", "stream-json"],
                )

        # 5. Antigravity CLI 1.5.11 real TUI screens detection
        scr = VtScreen(cols=100, rows=20)
        scr.feed("\x1b[2J\x1b[HWelcome to the Antigravity CLI.\r\n ⣷  Signing in...")
        self.assertEqual(detect_terminal_agent_state(scr)[0], "running")

        scr.feed("\x1b[2J\x1b[H> Verific… [Import this conversation? (y/n)]  35 steps")
        st_imp, reason_imp = detect_terminal_agent_state(scr)
        self.assertEqual(st_imp, "pending")
        self.assertIn("Import", reason_imp)

        scr.feed("\x1b[2J\x1b[H> Auto mode: edits & safe commands auto-approved\r\n? for shortcuts")
        self.assertEqual(detect_terminal_agent_state(scr)[0], "idle")

    def test_vt_screen_scrollback_and_widget_scroll_interaction(self):
        from unittest import mock
        from dass_aos.tui.pty_terminal import AgentTerminalWidget, PtySession, VtScreen

        scr = VtScreen(cols=50, rows=6)
        for i in range(1, 16):
            scr.feed(f"\x1b[36mLINEA_{i:02d}\x1b[0m\r\n")
        self.assertGreaterEqual(len(scr.scrollback), 9)
        self.assertNotIn("LINEA_01", scr.render_rich().plain)

        # Scroll up into scrollback preserving colors
        self.assertTrue(scr.scroll_view(10))
        self.assertGreater(scr.scroll_offset, 0)
        scrolled_rich = scr.render_rich(show_cursor=True)
        self.assertIn("LINEA_01", scrolled_rich.plain)
        self.assertTrue(any("#38bdf8" in str(sp.style).lower() for sp in scrolled_rich.spans))

        # Scroll back to bottom
        scr.reset_scroll()
        self.assertEqual(scr.scroll_offset, 0)
        self.assertIn("LINEA_15", scr.render_rich().plain)

        # Verify alt-screen + mouse wheel forwarding via AgentTerminalWidget
        widget = AgentTerminalWidget("")
        fake_pty = PtySession("t:scroll", ["cmd"], Path("."), cols=60, rows=8)
        fake_pty.alive = True
        fake_pty.screen.feed("\x1b[?1049h\x1b[?1000hClaude chat")
        self.assertTrue(fake_pty.screen.alt_screen)
        widget.pty_session = fake_pty
        with mock.patch.object(fake_pty, "write", return_value=True) as m_write:
            widget._handle_mouse_scroll(-1)  # scroll up
            m_write.assert_called_with("\x1b[5~", mark_user=True)
            widget._handle_mouse_scroll(1)  # scroll down
            m_write.assert_called_with("\x1b[6~", mark_user=True)


if __name__ == "__main__":
    unittest.main()



