"""Tests for `dass_aos.telemetry` and `aos tui` dependency handling (std-lib only)."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dass_aos.bootstrap import init_project
from dass_aos.cli import main as cli_main


class TestTelemetry(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.project_root = self.temp_dir / "repo"
        self.project_root.mkdir()
        init_project(self.project_root, project_name="demo-tui", tools=["claude-code", "antigravity"])
        # Keep active plans clean per test
        for p in (self.project_root / ".aos" / "plans" / "active").glob("*.md"):
            p.unlink()

        self.claude_home = self.temp_dir / "claude_home"
        self.agy_home = self.temp_dir / "agy_home"
        self.claude_home.mkdir()
        self.agy_home.mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_collect_telemetry_reads_aos_plans_specs_gotchas_and_lessons(self):
        from dass_aos.telemetry import collect_telemetry

        plan_file = self.project_root / ".aos" / "plans" / "active" / "001-demo.md"
        plan_file.write_text(
            "---\nid: 1\nstatus: active\n---\n\n"
            "# Plan: Feature — Demo TUI\n\n"
            "- [x] Fase 1: Discovery\n  - Nota subitem\n"
            "- [ ] Fase 2: Implementación\n"
            "- [ ] Fase 3: Verificación\n\n"
            "## Registro de Preguntas y Decisiones (Discovery Trail)\n"
            "- **Pregunta:** ¿Color azul?\n"
            "- **Decisión:**\n",
            encoding="utf-8",
        )
        gotcha_file = self.project_root / ".aos" / "knowledge" / "gotchas" / "cp1252-bug.md"
        gotcha_file.write_text(
            "---\ntitle: Windows cp1252 bug\nseverity: high\nstatus: abierta\n---\n\n# Windows cp1252 bug\n",
            encoding="utf-8",
        )
        ledger = self.project_root / ".aos" / "knowledge" / "lessons" / "LEDGER.md"
        ledger.write_text(
            "| Fecha | Artefacto | Evidencia | Efecto |\n"
            "|---|---|---|---|\n"
            "| 2026-11-16 | `telemetry.py` | test_x | Separación limpia |\n",
            encoding="utf-8",
        )

        snap = collect_telemetry(
            self.project_root,
            claude_home=self.claude_home,
            antigravity_home=self.agy_home,
        )

        self.assertEqual(snap.status_report.state, "Needs decision")
        self.assertEqual(len(snap.active_plans), 1)
        plan = snap.active_plans[0]
        self.assertEqual(plan.done, 1)
        self.assertEqual(plan.total, 3)
        self.assertEqual(plan.unanswered_questions, 1)
        self.assertEqual(len(plan.phases), 3)
        self.assertTrue(plan.phases[0].done)
        self.assertEqual(plan.phases[0].details, ["Nota subitem"])
        self.assertTrue(any(g["title"] == "Windows cp1252 bug" and g["severity"] == "high" for g in snap.gotchas))
        self.assertTrue(any("telemetry.py" in lesson for lesson in snap.lessons))

    def test_collect_telemetry_parses_claude_sessions_tasks_and_tolerates_corrupt_jsonl(self):
        from dass_aos.telemetry import collect_telemetry

        sessions_dir = self.claude_home / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "100.json").write_text(
            json.dumps({
                "pid": 100,
                "sessionId": "sess-match",
                "cwd": str(self.project_root),
                "status": "busy",
                "name": "build-tui",
                "entrypoint": "cli",
                "updatedAt": 1700000000000,
            }),
            encoding="utf-8",
        )
        # Other project session must be filtered out
        (sessions_dir / "200.json").write_text(
            json.dumps({
                "pid": 200,
                "sessionId": "sess-other",
                "cwd": str(self.temp_dir / "other-repo"),
                "status": "idle",
            }),
            encoding="utf-8",
        )

        # Encoded project directory (Claude Code maps every non-alphanumeric char to "-")
        from dass_aos.telemetry import _encode_claude_cwd

        proj_dir = self.claude_home / "projects" / _encode_claude_cwd(self.project_root)
        proj_dir.mkdir(parents=True)
        jsonl_path = proj_dir / "sess-match.jsonl"
        jsonl_path.write_text(
            "\n".join([
                json.dumps({"type": "ai-title", "aiTitle": "Implementar TUI", "sessionId": "sess-match"}),
                json.dumps({
                    "type": "assistant",
                    "timestamp": "2026-11-16T10:00:00Z",
                    "message": {
                        "content": [
                            {"type": "tool_use", "name": "Edit", "input": {"file_path": "dass_aos/cli.py"}},
                            {"type": "tool_use", "name": "Agent", "input": {"description": "Explorer"}},
                        ]
                    },
                }),
                json.dumps({
                    "type": "cost-state",
                    "sessionId": "sess-match",
                    "totalCostUSD": 0.12,
                    "totalLinesAdded": 42,
                }),
                "{corrupt partial line being written",
            ]) + "\n",
            encoding="utf-8",
        )

        tasks_dir = self.claude_home / "tasks" / "sess-match"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "1.json").write_text(
            json.dumps({"id": "1", "subject": "Run unit tests", "status": "in_progress"}),
            encoding="utf-8",
        )

        snap = collect_telemetry(
            self.project_root,
            claude_home=self.claude_home,
            antigravity_home=self.agy_home,
        )

        claude_sessions = [s for s in snap.sessions if s.tool == "claude-code"]
        self.assertEqual(len(claude_sessions), 1)
        sess = claude_sessions[0]
        self.assertEqual(sess.session_id, "sess-match")
        self.assertEqual(sess.title, "Implementar TUI")
        self.assertEqual(sess.status, "busy")
        self.assertIn("Edit", sess.recent_tools)
        self.assertIn("Explorer", sess.subagents)
        self.assertEqual(len(sess.tasks), 1)
        self.assertEqual(sess.tasks[0].status, "in_progress")

    def test_collect_telemetry_handles_iso_or_invalid_claude_updated_at(self):
        from dass_aos.telemetry import collect_telemetry

        sessions_dir = self.claude_home / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "101.json").write_text(
            json.dumps({
                "pid": 101,
                "sessionId": "sess-iso",
                "cwd": str(self.project_root),
                "status": "idle",
                "updatedAt": "2026-11-16T10:30:00Z",
            }),
            encoding="utf-8",
        )
        snap = collect_telemetry(self.project_root, claude_home=self.claude_home, antigravity_home=self.agy_home)
        self.assertEqual(len(snap.sessions), 1)
        self.assertEqual(snap.sessions[0].session_id, "sess-iso")
        self.assertGreater(snap.sessions[0].updated_at, 0.0)

    def test_collect_telemetry_parses_antigravity_transcript_and_background_tasks(self):
        from dass_aos.telemetry import collect_telemetry

        conv_id = "conv-1234"
        seen_file = self.project_root / ".aos" / "native" / "antigravity-seen.txt"
        seen_file.parent.mkdir(parents=True, exist_ok=True)
        seen_file.write_text(f"{conv_id}\n", encoding="utf-8")

        brain_dir = self.agy_home / "brain" / conv_id / ".system_generated"
        (brain_dir / "logs").mkdir(parents=True)
        (brain_dir / "tasks").mkdir(parents=True)

        (brain_dir / "logs" / "transcript.jsonl").write_text(
            "\n".join([
                json.dumps({
                    "step_index": 0,
                    "source": "USER_EXPLICIT",
                    "type": "USER_INPUT",
                    "status": "DONE",
                    "created_at": "2026-11-16T10:35:00Z",
                    "content": "Haz la TUI",
                }),
                json.dumps({
                    "step_index": 1,
                    "source": "MODEL",
                    "type": "PLANNER_RESPONSE",
                    "status": "DONE",
                    "created_at": "2026-11-16T10:36:00Z",
                    "tool_calls": [
                        {"name": "read_file", "arguments": {"Path": str(self.project_root / "dass_aos" / "cli.py")}},
                        {"name": "invoke_subagent", "arguments": {"Role": "UI Designer", "TypeName": "self"}},
                    ],
                }),
                "{truncated-json",
            ]) + "\n",
            encoding="utf-8",
        )
        (brain_dir / "tasks" / "task-14.log").write_text(
            "line 1\nline 2\nAll checks passed!\n",
            encoding="utf-8",
        )

        # Unrelated Antigravity conversation should be ignored
        other_logs = self.agy_home / "brain" / "other-conv" / ".system_generated" / "logs"
        other_logs.mkdir(parents=True)
        (other_logs / "transcript.jsonl").write_text(
            json.dumps({"step_index": 0, "content": "working on /tmp/unrelated"}) + "\n",
            encoding="utf-8",
        )

        snap = collect_telemetry(
            self.project_root,
            claude_home=self.claude_home,
            antigravity_home=self.agy_home,
        )

        agy_sessions = [s for s in snap.sessions if s.tool == "antigravity"]
        self.assertEqual(len(agy_sessions), 1)
        sess = agy_sessions[0]
        self.assertEqual(sess.session_id, conv_id)
        self.assertIn("read_file", sess.recent_tools)
        self.assertTrue(any("UI Designer" in sub for sub in sess.subagents))
        self.assertEqual(len(sess.tasks), 1)
        self.assertEqual(sess.tasks[0].id, "task-14")
        self.assertIn("All checks passed!", sess.tasks[0].tail_lines[-1])

    def test_collect_telemetry_reads_git_changes_and_diff_snapshots(self):
        from dass_aos.telemetry import collect_telemetry, diff_snapshots

        subprocess.run(["git", "init"], cwd=str(self.project_root), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(self.project_root), check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(self.project_root), check=True)
        readme = self.project_root / "README.md"
        readme.write_text("v1\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=str(self.project_root), check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(self.project_root), check=True, capture_output=True)

        plan_file = self.project_root / ".aos" / "plans" / "active" / "001-demo.md"
        plan_file.write_text("# Plan\n\n- [ ] Fase 1: A\n- [ ] Fase 2: B\n", encoding="utf-8")

        prev = collect_telemetry(self.project_root, claude_home=self.claude_home, antigravity_home=self.agy_home)
        self.assertTrue(prev.git.available)

        # Simulate agent progress: complete phase 1 and modify README.md
        plan_file.write_text("# Plan\n\n- [x] Fase 1: A\n- [ ] Fase 2: B\n", encoding="utf-8")
        readme.write_text("v2\n", encoding="utf-8")

        curr = collect_telemetry(self.project_root, claude_home=self.claude_home, antigravity_home=self.agy_home)
        self.assertFalse(curr.git.clean)
        self.assertTrue(any(c.path == "README.md" for c in curr.git.changes))

        events = diff_snapshots(prev, curr)
        messages = " | ".join(e.message for e in events)
        self.assertIn("1/2", messages)
        self.assertIn("README.md", messages)

    def test_cli_tui_reports_missing_optional_dependency_gracefully(self):
        import io
        from contextlib import redirect_stderr

        buf = io.StringIO()
        with mock.patch("dass_aos.tui._import_textual", side_effect=ImportError("No module named 'textual'")):
            with redirect_stderr(buf):
                code = cli_main(["tui", "--project-root", str(self.project_root)])
        self.assertNotEqual(code, 0)
        self.assertIn("dass-aos[tui]", buf.getvalue())

    def test_collect_telemetry_fast_tick_reuses_slow_checks_and_updates_plan(self):
        from dass_aos.telemetry import collect_telemetry

        plan_file = self.project_root / ".aos" / "plans" / "active" / "001-demo.md"
        plan_file.write_text("# Plan\n\n- [ ] Fase 1: A\n- [ ] Fase 2: B\n", encoding="utf-8")

        first = collect_telemetry(
            self.project_root,
            claude_home=self.claude_home,
            antigravity_home=self.agy_home,
            include_slow=True,
        )
        plan_file.write_text("# Plan\n\n- [x] Fase 1: A\n- [ ] Fase 2: B\n", encoding="utf-8")

        with mock.patch("dass_aos.telemetry.collect_findings", side_effect=AssertionError("should not rerun doctor")):
            second = collect_telemetry(
                self.project_root,
                claude_home=self.claude_home,
                antigravity_home=self.agy_home,
                prev_snapshot=first,
                include_slow=False,
            )

        self.assertEqual(second.active_plans[0].done, 1)
        self.assertEqual(second.doctor_findings, first.doctor_findings)

    def test_collect_telemetry_aggregates_tokens_without_double_counting_claude_and_agy(self):
        from dass_aos.telemetry import collect_telemetry

        # 1. Claude session with duplicate requestId streaming lines
        from dass_aos.telemetry import _encode_claude_cwd

        proj_dir = self.claude_home / "projects" / _encode_claude_cwd(self.project_root)
        proj_dir.mkdir(parents=True)
        claude_jsonl = proj_dir / "sess-tok.jsonl"
        claude_jsonl.write_text(
            "\n".join([
                json.dumps({
                    "type": "assistant",
                    "requestId": "req-1",
                    "timestamp": "2026-11-16T12:00:00Z",
                    "message": {
                        "usage": {
                            "input_tokens": 100,
                            "cache_creation_input_tokens": 500,
                            "cache_read_input_tokens": 2000,
                            "output_tokens": 300,
                            "output_tokens_details": {"thinking_tokens": 80},
                        },
                        "content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "a.py"}}],
                    },
                }),
                json.dumps({
                    "type": "assistant",
                    "requestId": "req-1",
                    "timestamp": "2026-11-16T12:00:01Z",
                    "message": {
                        "usage": {
                            "input_tokens": 100,
                            "cache_creation_input_tokens": 500,
                            "cache_read_input_tokens": 2000,
                            "output_tokens": 300,
                            "output_tokens_details": {"thinking_tokens": 80},
                        },
                        "content": [{"type": "tool_use", "name": "Grep", "input": {"pattern": "foo"}}],
                    },
                }),
                json.dumps({
                    "type": "cost-state",
                    "sessionId": "sess-tok",
                    "totalCostUSD": 0.45,
                }),
            ]) + "\n",
            encoding="utf-8",
        )

        # 2. Antigravity session with two turns
        conv_id = "conv-tok"
        seen_file = self.project_root / ".aos" / "native" / "antigravity-seen.txt"
        seen_file.parent.mkdir(parents=True, exist_ok=True)
        seen_file.write_text(f"{conv_id}\n", encoding="utf-8")
        agy_logs = self.agy_home / "brain" / conv_id / ".system_generated" / "logs"
        agy_logs.mkdir(parents=True)
        agy_jsonl = agy_logs / "transcript.jsonl"
        agy_jsonl.write_text(
            "\n".join([
                json.dumps({
                    "step_index": 1,
                    "type": "PLANNER_RESPONSE",
                    "status": "DONE",
                    "created_at": "2026-11-16T12:01:00Z",
                    "input_tokens": 1000,
                    "cache_read_tokens": 0,
                    "output_tokens": 200,
                    "tool_calls": [{"name": "run_command", "arguments": {"CommandLine": "pytest"}}],
                }),
                json.dumps({
                    "step_index": 2,
                    "type": "PLANNER_RESPONSE",
                    "status": "DONE",
                    "created_at": "2026-11-16T12:02:00Z",
                    "input_tokens": 400,
                    "cache_read_tokens": 1200,
                    "output_tokens": 100,
                    "tool_calls": [{"name": "edit_file", "arguments": {"Path": "x.py"}}],
                }),
            ]) + "\n",
            encoding="utf-8",
        )

        snap = collect_telemetry(self.project_root, claude_home=self.claude_home, antigravity_home=self.agy_home)
        tok = snap.tokens
        # Claude (req-1 counted ONCE!): input_new = 600, cache_read = 2000, out = 300, thinking = 80
        # Agy (2 steps): input_new = 1400, cache_read = 1200, out = 300
        self.assertEqual(tok.input_tokens, 2000)
        self.assertEqual(tok.cache_read_tokens, 3200)
        self.assertEqual(tok.output_tokens, 600)
        self.assertEqual(tok.thinking_tokens, 80)
        self.assertAlmostEqual(tok.total_cost_usd, 0.45, places=2)

        by_tool = {item.name: item for item in tok.by_tool}
        self.assertIn("run_command", by_tool)
        self.assertEqual(by_tool["run_command"].input_tokens, 1000)
        self.assertEqual(by_tool["run_command"].output_tokens, 200)
        # req-1 had Read + Grep: 600 input + 300 output split cleanly without double counting
        self.assertEqual(by_tool["Read"].input_tokens + by_tool["Grep"].input_tokens, 600)
        self.assertGreater(len(tok.by_category), 0)
        self.assertGreater(len(tok.harness_weights), 0)

        # Incremental append on Antigravity transcript adds only the new turn
        with agy_jsonl.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "step_index": 3,
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": "2026-11-16T12:03:00Z",
                "input_tokens": 300,
                "cache_read_tokens": 1600,
                "output_tokens": 50,
                "tool_calls": [{"name": "run_command", "arguments": {"CommandLine": "ruff"}}],
            }) + "\n")

        snap2 = collect_telemetry(self.project_root, claude_home=self.claude_home, antigravity_home=self.agy_home)
        self.assertEqual(snap2.tokens.input_tokens, 2300)
        self.assertEqual(snap2.tokens.output_tokens, 650)

    def test_tokens_are_scoped_to_this_project_workspace(self):
        import os
        import sqlite3
        import time

        from dass_aos.telemetry import _encode_claude_cwd, collect_telemetry

        def claude_turn(msg_id, req_id, inp, out):
            return json.dumps({"type": "assistant", "requestId": req_id, "message": {
                "id": msg_id, "usage": {"input_tokens": inp, "output_tokens": out}, "content": []}})

        # Claude: two sessions + one subagent transcript; session B replays A's call (resume).
        proj_dir = self.claude_home / "projects" / _encode_claude_cwd(self.project_root)
        (proj_dir / "sess-b" / "subagents").mkdir(parents=True)
        (proj_dir / "sess-a.jsonl").write_text(claude_turn("m1", "r1", 100, 10) + "\n", encoding="utf-8")
        (proj_dir / "sess-b.jsonl").write_text(
            claude_turn("m1", "r1", 100, 10) + "\n" + claude_turn("m2", "r2", 50, 5) + "\n", encoding="utf-8")
        (proj_dir / "sess-b" / "subagents" / "agent-x.jsonl").write_text(
            claude_turn("m3", "r3", 7, 1) + "\n", encoding="utf-8")
        old = time.time() - 100
        os.utime(proj_dir / "sess-a.jsonl", (old, old))
        # Another project's Claude transcripts must be ignored.
        other = self.claude_home / "projects" / "c--elsewhere"
        other.mkdir(parents=True)
        (other / "x.jsonl").write_text(claude_turn("m9", "r9", 9999, 9999) + "\n", encoding="utf-8")

        # Antigravity: workspace comes from its own index, not from mentions of the path.
        def agy_conv(conv_id, text):
            logs = self.agy_home / "brain" / conv_id / ".system_generated" / "logs"
            logs.mkdir(parents=True)
            (logs / "transcript.jsonl").write_text(json.dumps(
                {"step_index": 0, "type": "PLANNER_RESPONSE", "content": text,
                 "input_tokens": 1000, "output_tokens": 100}) + "\n", encoding="utf-8")

        agy_conv("mine", "hola")
        agy_conv("mentions-me", f"leyendo {self.project_root.resolve()}")  # other workspace
        root_uri = self.project_root.resolve().as_uri().replace(":", "%3A", 2).replace("%3A", ":", 1)
        con = sqlite3.connect(str(self.agy_home / "conversation_summaries.db"))
        con.execute("CREATE TABLE conversation_summaries (conversation_id text, workspace_uris text)")
        con.executemany("INSERT INTO conversation_summaries VALUES (?, ?)", [
            ("mine", json.dumps([root_uri])),
            ("mentions-me", json.dumps(["file:///c%3A/otro/proyecto"])),
        ])
        con.commit()
        con.close()

        tok = collect_telemetry(self.project_root, claude_home=self.claude_home, antigravity_home=self.agy_home).tokens
        by_id = {s.session_id: s for s in tok.by_session}
        self.assertEqual(set(by_id), {"sess-a", "sess-b", "mine"})
        self.assertEqual(by_id["sess-a"].input_tokens, 100)  # owns the replayed call
        self.assertEqual(by_id["sess-b"].input_tokens, 57)  # r2 + subagent r3, not r1 again
        self.assertEqual(tok.input_tokens, 100 + 57 + 1000)
        self.assertEqual(tok.output_tokens, 10 + 6 + 100)
