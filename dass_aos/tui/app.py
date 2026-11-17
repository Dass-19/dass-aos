"""Textual TUI application for DASS-AOS (`aos tui`)."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from rich.markdown import Markdown as RichMarkdown
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Input,
    Markdown,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)

from ..constants import VERSION
from ..rag import search_context
from ..telemetry import (
    AgentSessionInfo,
    AgentTaskInfo,
    LiveEvent,
    TelemetrySnapshot,
    collect_telemetry,
    diff_snapshots,
    read_git_file_diff,
)
from .widgets import (
    brand_lockup,
    agent_badge,
    compact_age,
    format_activity_row,
    format_diff_lines,
    format_knowledge_zoom,
    kind_text,
    level_text,
    severity_text,
    status_text,
    format_output_line,
    markdown_diff,
    format_kpi_agents,
    format_kpi_git,
    format_kpi_health,
    format_kpi_plan,
    format_kpi_tok_cache,
    format_kpi_tok_context,
    format_kpi_tok_input,
    format_kpi_tok_output,
    format_live_event,
    format_pulse_and_distribution,
    format_session_detail_summary,
    format_tokens_compact,
    token_bar,
)

_SLOW_CHECK_INTERVAL_SECONDS = 10.0
_THEMES = ("theme-cyan", "theme-emerald", "theme-violet")


def _cell_sig(cell: Any) -> str:
    return cell.plain if isinstance(cell, Text) else str(cell)


class HelpScreen(ModalScreen[None]):
    """Keyboard & navigation reference modal (`?`)."""

    BINDINGS = [
        Binding("escape", "dismiss", "Cerrar"),
        Binding("question_mark", "dismiss", "Cerrar"),
        Binding("q", "dismiss", "Cerrar"),
    ]

    def compose(self) -> ComposeResult:
        box = Vertical(id="help-dialog")
        box.border_title = "◆ DASS·AOS · Atajos y Ayuda"
        with box:
            help_md = (
                "### Navegación\n"
                "- `1`..`7` — Cambiar entre Resumen, Planes, Agentes, Git, RAG/Salud, Consola y Tokens\n"
                "- `↑` / `↓` — Mover cursor en tablas (actualiza vista previa al instante)\n"
                "- `/` — Saltar al buscador RAG (`aos context`)\n\n"
                "### Control en Vivo (estilo Gonzo)\n"
                "- `Espacio` — Pausar / reanudar el refresco automático en tiempo real\n"
                "- `z` — Maximizar (zoom) el panel activo (`Esc` para salir)\n"
                "- `r` — Forzar refresco completo (incluye `aos doctor`)\n"
                "- `t` — Cambiar tema visual (`Cyan` · `Emerald` · `Violet`)\n\n"
                "### Acciones del Motor\n"
                "- `v` `aos verify` · `s` `aos scan --dry-run` · `y` `aos sync` · `f` `aos refresh`\n"
                "- `q` — Salir de la TUI (pulsa `Esc` o `?` para cerrar esta ventana)"
            )
            yield Markdown(help_md)


class ZoomScreen(ModalScreen[None]):
    """Fullscreen reader modal (`z`) for logs, diffs, docs, or activity feeds."""

    BINDINGS = [
        Binding("escape", "dismiss", "Cerrar"),
        Binding("z", "dismiss", "Cerrar"),
        Binding("q", "dismiss", "Cerrar"),
    ]

    def __init__(self, title: str, content: Any, is_markdown: bool = False) -> None:
        super().__init__()
        self._zoom_title = title
        self._zoom_content = content
        self._is_markdown = is_markdown

    def compose(self) -> ComposeResult:
        box = Vertical(id="zoom-dialog")
        box.border_title = f"{self._zoom_title}  (Esc / z para volver)"
        with box:
            with VerticalScroll(id="zoom-scroll"):
                if self._is_markdown:
                    yield Markdown(str(self._zoom_content))
                else:
                    yield Static(self._zoom_content)


class AosTuiApp(App):
    """Real-time monitoring and control center for DASS-AOS."""

    CSS_PATH = Path(__file__).with_name("styles.tcss")
    TITLE = "DASS-AOS Monitor"

    BINDINGS = [
        Binding("1", "switch_tab('tab-overview')", "Resumen", show=True),
        Binding("2", "switch_tab('tab-plans')", "Planes", show=True),
        Binding("3", "switch_tab('tab-agents')", "Agentes", show=True),
        Binding("4", "switch_tab('tab-git')", "Git", show=True),
        Binding("5", "switch_tab('tab-knowledge')", "RAG/Salud", show=True),
        Binding("6", "switch_tab('tab-console')", "Consola", show=True),
        Binding("7", "switch_tab('tab-tokens')", "Tokens", show=True),
        Binding("space", "toggle_pause", "Pausar", show=True),
        Binding("z", "toggle_zoom", "Zoom", show=True),
        Binding("r", "refresh_now", "Refrescar", show=True),
        Binding("v", "run_verify", "Verify", show=True),
        Binding("s", "run_scan", "Scan", show=True),
        Binding("y", "run_sync", "Sync", show=True),
        Binding("f", "run_refresh_cmd", "Refresh", show=False),
        Binding("/", "focus_rag", "Buscar", show=True),
        Binding("t", "cycle_theme", "Tema", show=False),
        Binding("question_mark", "show_help", "Ayuda", show=True),
        Binding("q", "quit", "Salir", show=True),
    ]

    def __init__(
        self,
        project_root: Path,
        interval: float = 1.5,
        claude_home: Optional[Path] = None,
        antigravity_home: Optional[Path] = None,
    ) -> None:
        super().__init__()
        self.project_root = project_root.resolve()
        self.interval = max(0.5, float(interval))
        self.claude_home = claude_home
        self.antigravity_home = antigravity_home

        self.snapshot: Optional[TelemetrySnapshot] = None
        self.events: List[LiveEvent] = []
        self._pulse_history: List[int] = []
        self._refreshing = False
        self._runner_busy = False
        self._paused = False
        self._theme_idx = 0
        self._last_slow_check_ts = 0.0

        self._doc_paths: Dict[str, Path] = {}
        self._selected_doc_key: Optional[str] = None
        self._last_doc_sig: Optional[Tuple[str, int]] = None

        self._sessions_by_key: Dict[str, AgentSessionInfo] = {}
        self._selected_session_key: Optional[str] = None
        self._last_session_sig: Optional[tuple] = None

        self._tasks_by_key: Dict[str, AgentTaskInfo] = {}
        self._selected_task_key: Optional[str] = None
        self._last_task_tail_sig: Optional[tuple] = None

        self._selected_git_path: Optional[str] = None
        self._last_diff_sig: Optional[tuple] = None

        self._table_sigs: Dict[str, List[Tuple[Optional[str], Tuple[str, ...]]]] = {}
        self._runner_jobs: List[AgentTaskInfo] = []
        self._active_proc: Optional[subprocess.Popen] = None
        self._rag_initialized = False
        self._rag_last: Any = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="top-bar"):
            yield Static(f"   AOS version:  {VERSION}\nWorking folder:  {self.project_root}", id="top-project")
            yield Static(brand_lockup(), id="brand-logo")

        with TabbedContent(initial="tab-overview", id="main-tabs"):
            # 1. Dashboard / Resumen
            with TabPane("Resumen", id="tab-overview"):
                with Horizontal(classes="kpi-row"):
                    yield Static("", id="kpi-plan", classes="kpi-card")
                    yield Static("", id="kpi-agents", classes="kpi-card")
                    yield Static("", id="kpi-git", classes="kpi-card")
                    yield Static("", id="kpi-health", classes="kpi-card kpi-card-last")
                with Horizontal(classes="dash-split"):
                    with Vertical(id="dash-left"):
                        with Vertical(id="dash-phases-box", classes="panel"):
                            yield DataTable(id="dash-phases-table")
                        with Vertical(id="dash-agents-box", classes="panel"):
                            yield DataTable(id="dash-agents-table")
                    with Vertical(id="dash-right"):
                        with Vertical(id="dash-feed-box", classes="panel"):
                            yield RichLog(id="live-feed-log", wrap=True, highlight=False, markup=False)
                        with Vertical(id="dash-pulse-box", classes="panel"):
                            yield Static("", id="dash-pulse-content")

            # 2. Planes & Specs
            with TabPane("Planes & Specs", id="tab-plans"):
                with Horizontal(classes="split-h"):
                    with Vertical(classes="col-left-narrow panel", id="plans-list-box"):
                        yield DataTable(id="plans-table")
                    with Vertical(classes="col-right-wide"):
                        yield Static("Selecciona un plan, spec o ADR.", id="plans-summary-bar")
                        with VerticalScroll(id="plans-doc-scroll"):
                            yield Markdown("", id="plans-markdown")

            # 3. Agentes & Tasks
            with TabPane("Agentes & Tasks", id="tab-agents"):
                with Horizontal(classes="split-h"):
                    with Vertical(classes="col-left-mid"):
                        with Vertical(id="agents-sessions-box", classes="panel"):
                            yield DataTable(id="agents-sessions-table")
                        with Vertical(id="agents-tasks-box", classes="panel"):
                            yield DataTable(id="agents-tasks-table")
                    with Vertical(classes="col-right-wide"):
                        with Vertical(id="agents-activity-box", classes="panel"):
                            yield Static("", id="agents-session-summary")
                            yield RichLog(id="agents-activity-log", wrap=True, markup=False)
                        with Vertical(id="agents-log-box", classes="panel"):
                            yield RichLog(id="agents-task-log", wrap=True, markup=False)

            # 4. Git & Diff
            with TabPane("Git & Diff", id="tab-git"):
                with Horizontal(classes="split-h"):
                    with Vertical(classes="col-left-mid"):
                        with Vertical(id="git-files-box", classes="panel"):
                            yield DataTable(id="git-files-table")
                        with Vertical(id="git-commits-box", classes="panel"):
                            yield RichLog(id="git-commits-log", wrap=True, markup=False, auto_scroll=False)
                    with Vertical(id="git-diff-box", classes="col-right-wide panel"):
                        yield RichLog(id="git-diff-log", wrap=False, markup=False, auto_scroll=False)

            # 5. Conocimiento & Doctor
            with TabPane("RAG & Salud", id="tab-knowledge"):
                with Horizontal(id="rag-search-row"):
                    yield Input(
                        placeholder="Buscar en .aos/ con aos context (gotchas, ADRs, specs, contratos)...",
                        id="rag-input",
                    )
                    yield Static("RAG: --", id="rag-mode-badge")
                with Horizontal(id="knowledge-grid"):
                    with Vertical(id="knowledge-left"):
                        with Vertical(id="rag-results-box", classes="panel"):
                            yield DataTable(id="rag-results-table")
                        with Vertical(id="gotchas-box", classes="panel"):
                            yield DataTable(id="gotchas-table")
                    with Vertical(id="knowledge-right"):
                        with Vertical(id="doctor-box", classes="panel"):
                            yield DataTable(id="doctor-table")
                        with Vertical(id="native-box", classes="panel"):
                            yield RichLog(id="native-log", wrap=True, markup=False, auto_scroll=False)

            # 6. Consola / Acciones
            with TabPane("Consola", id="tab-console"):
                with Horizontal(id="runner-toolbar"):
                    yield Button("Verify (v)", id="btn-verify")
                    yield Button("Scan Dry-Run (s)", id="btn-scan")
                    yield Button("Sync (y)", id="btn-sync")
                    yield Button("Refresh (f)", id="btn-refresh-cmd")
                    yield Button("Doctor", id="btn-doctor")
                yield Static("Listo para ejecutar comandos de DASS-AOS.", id="runner-status-bar")
                with Vertical(id="runner-output-box", classes="panel"):
                    yield RichLog(id="runner-log", wrap=True, markup=False)

            # 7. Tokens & Desglose de Gasto
            with TabPane("Tokens", id="tab-tokens"):
                with Horizontal(classes="kpi-row"):
                    yield Static("", id="kpi-tok-in", classes="kpi-card")
                    yield Static("", id="kpi-tok-cache", classes="kpi-card")
                    yield Static("", id="kpi-tok-out", classes="kpi-card")
                    yield Static("", id="kpi-tok-ctx", classes="kpi-card kpi-card-last")
                with Horizontal(id="tokens-grid"):
                    with Vertical(id="tokens-left"):
                        with Vertical(id="tokens-cat-box", classes="panel"):
                            yield DataTable(id="tokens-cat-table")
                        with Vertical(id="tokens-tools-box", classes="panel"):
                            yield DataTable(id="tokens-tools-table")
                    with Vertical(id="tokens-right"):
                        with Vertical(id="tokens-sessions-box", classes="panel"):
                            yield DataTable(id="tokens-sessions-table")
                        with Vertical(id="tokens-harness-box", classes="panel"):
                            yield DataTable(id="tokens-harness-table")

        yield Footer()

    def on_mount(self) -> None:
        self._init_panel_titles()
        self._init_tables()
        self._refresh_worker(force_slow=True)
        self.set_interval(self.interval, self._tick_refresh)

    def on_unmount(self) -> None:
        proc = self._active_proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

    def _init_panel_titles(self) -> None:
        titles = {
            "#top-bar": "Agent Operating System",
            "#kpi-plan": "Estado & Plan",
            "#kpi-agents": "Agentes & Tasks",
            "#kpi-git": "Git Workspace",
            "#kpi-health": "Salud Harness",
            "#dash-phases-box": "Plan Activo",
            "#dash-agents-box": "Sesiones & Tasks Activas",
            "#dash-pulse-box": "Pulso & Distribución",
            "#dash-feed-box": "Actividad en Tiempo Real",
            "#plans-list-box": "Planes · Specs · ADRs",
            "#plans-doc-scroll": "Vista de Documento",
            "#agents-sessions-box": "Sesiones (Claude Code & Antigravity)",
            "#agents-tasks-box": "Tasks en Background & Workers",
            "#agents-activity-box": "Timeline del Agente",
            "#agents-log-box": "Tail de Log en Vivo",
            "#git-files-box": "Cambios en Workspace (Git)",
            "#git-commits-box": "Commits Recientes",
            "#git-diff-box": "Diff del Archivo Seleccionado",
            "#rag-results-box": "Resultados RAG (aos context)",
            "#gotchas-box": "Gotchas Prioritarios",
            "#doctor-box": "Auditoría Harness (aos doctor)",
            "#native-box": "Nativos · Dependencias · Lecciones",
            "#runner-output-box": "Salida de Ejecución en Vivo",
            "#kpi-tok-in": "Input Nuevo",
            "#kpi-tok-cache": "Cache Read",
            "#kpi-tok-out": "Output & Thinking",
            "#kpi-tok-ctx": "Contexto & Harness",
            "#tokens-cat-box": "Qué Gasta Más (por Categoría)",
            "#tokens-tools-box": "Top Tools Consumidoras",
            "#tokens-sessions-box": "Consumo por Sesión",
            "#tokens-harness-box": "Peso del Harness .aos/ (est.)",
        }
        for selector, title in titles.items():
            self.query_one(selector).border_title = title
        legend = "[bold #d9b15f]CC[/] Claude Code  [bold #8aa8cc]AG[/] Antigravity"
        self.query_one("#agents-sessions-box").border_subtitle = legend
        self.query_one("#tokens-sessions-box").border_subtitle = legend
        self.query_one("#agents-tasks-box").border_subtitle = legend + "  [bold #9aa59c]TUI[/] Consola"

    def _init_tables(self) -> None:
        specs = [
            ("#dash-phases-table", ("Estado", "Fase / Subtarea")),
            ("#dash-agents-table", ("", "Sesión / Task", "Estado", "Act.")),
            ("#plans-table", ("Tipo", "Archivo", "Info")),
            ("#agents-sessions-table", ("", "Sesión", "Estado", "Act.")),
            ("#agents-tasks-table", ("", "Task", "Estado", "Edad")),
            ("#git-files-table", ("Flag", "Archivo")),
            ("#rag-results-table", ("Tipo", "Score", "Título › Sección")),
            ("#gotchas-table", ("Gravedad", "Gotcha", "Fecha")),
            ("#doctor-table", ("Nivel", "Área", "Detalle")),
            ("#tokens-cat-table", ("Categoría", "Input", "Output", "Total", "%", "Uso")),
            ("#tokens-tools-table", ("Tool", "Calls", "Input", "Output", "%", "Uso")),
            ("#tokens-sessions-table", ("", "Sesión", "In", "Cache", "Out", "Ctx", "$")),
            ("#tokens-harness-table", ("Área", "Clase", "Arch.", "~Tokens")),
        ]
        for selector, cols in specs:
            table = self.query_one(selector, DataTable)
            table.cursor_type = "row"
            table.zebra_stripes = True
            # Cell colors (bars, severities, numbers) win over cursor/hover; those only tint the row.
            table.cursor_foreground_priority = "renderable"
            table.add_columns(*cols)

    def _main_query(self, selector: str, expect_type: Any = None) -> Any:
        """Query the base dashboard screen even when a modal overlay is stacked."""
        root = self.screen_stack[0] if self.screen_stack else self.screen
        if expect_type is not None:
            return root.query_one(selector, expect_type)
        return root.query_one(selector)

    def _sync_table(
        self,
        selector: str,
        rows: List[Tuple[Optional[str], Sequence[Any]]],
        preserve_key: Optional[str] = None,
    ) -> None:
        """Update a DataTable only when its content changes, preserving cursor row."""
        sig = [(key, tuple(_cell_sig(c) for c in cells)) for key, cells in rows]
        if self._table_sigs.get(selector) == sig:
            return
        self._table_sigs[selector] = sig

        table = self._main_query(selector, DataTable)
        target_row_idx: Optional[int] = None
        if preserve_key is not None:
            for idx, (key, _) in enumerate(rows):
                if key == preserve_key:
                    target_row_idx = idx
                    break
        elif table.row_count > 0:
            target_row_idx = min(table.cursor_row, max(len(rows) - 1, 0))

        table.clear()
        for key, cells in rows:
            if key is not None:
                table.add_row(*cells, key=key)
            else:
                table.add_row(*cells)

        if target_row_idx is not None and rows:
            table.move_cursor(row=target_row_idx, animate=False)

    def _tick_refresh(self) -> None:
        if self._paused:
            return
        if not self._refreshing:
            self._refresh_worker(force_slow=False)

    def action_toggle_pause(self) -> None:
        self._paused = not self._paused
        if self.snapshot is not None:
            self._update_header(self.snapshot)
        state = "pausado (Espacio para reanudar)" if self._paused else "reanudado en vivo"
        self.notify(f"Monitor {state}", timeout=2.0)

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_cycle_theme(self) -> None:
        old_cls = _THEMES[self._theme_idx]
        self._theme_idx = (self._theme_idx + 1) % len(_THEMES)
        new_cls = _THEMES[self._theme_idx]
        self.screen.remove_class(old_cls)
        self.screen.add_class(new_cls)
        label = new_cls.replace("theme-", "").capitalize()
        self.notify(f"Tema: {label}", timeout=1.5)

    def _zoom_payload(self) -> Tuple[str, Any, bool]:
        tab = self.query_one("#main-tabs", TabbedContent).active
        focused_id = self.focused.id if self.focused else ""

        if tab == "tab-plans" and self._selected_doc_key in self._doc_paths:
            path = self._doc_paths[self._selected_doc_key]
            text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
            return path.name, text, True
        if tab == "tab-git" and self._selected_git_path:
            diff_text = read_git_file_diff(self.project_root, self._selected_git_path, max_lines=1000)
            md_path = self.project_root / self._selected_git_path
            if md_path.suffix.lower() == ".md" and md_path.is_file():
                doc = md_path.read_text(encoding="utf-8", errors="replace")
                body = f"## Cambios\n\n{markdown_diff(diff_text, doc)}\n\n---\n\n## Documento\n\n{doc}"
                return f"Git Diff · {self._selected_git_path}", body, True
            out = Text()
            for ln in format_diff_lines(diff_text):
                out.append_text(ln)
                out.append("\n")
            return f"Git Diff · {self._selected_git_path}", out, False
        if tab == "tab-agents":
            if focused_id == "agents-activity-log" or (not self._selected_task_key and self._selected_session_key):
                sess = self._sessions_by_key.get(self._selected_session_key or "")
                out = format_session_detail_summary(sess)
                out.append("\n\n")
                for item in (sess.activities if sess else []):
                    out.append(f"{item.timestamp} [{item.kind}] {item.summary}\n")
                return f"Sesión · {sess.title if sess else '-'}", out, False
            task = self._tasks_by_key.get(self._selected_task_key or "")
            lines = list(task.tail_lines) if task else []
            out = Text()
            for ln in lines:
                out.append_text(format_output_line(ln))
                out.append("\n")
            return f"Log · {task.title if task else 'sin task'}", out or Text("(sin salida)"), False
        if tab == "tab-console" and self._runner_jobs:
            job = self._runner_jobs[0]
            out = Text()
            for ln in job.tail_lines:
                out.append_text(format_output_line(ln))
                out.append("\n")
            return f"Consola · {job.title}", out, False
        if tab == "tab-knowledge" and self.snapshot:
            out = format_knowledge_zoom(self._rag_last, self.snapshot.doctor_findings, self.snapshot.gotchas)
            return "RAG & Salud del Harness", out, False

        if tab == "tab-tokens" and self.snapshot:
            tok = self.snapshot.tokens
            lines_md = [
                "### Resumen de Tokens",
                f"- **Input nuevo**: {tok.input_tokens:,} · **Cache read**: {tok.cache_read_tokens:,} · **Output**: {tok.output_tokens:,}",
                "\n### Qué Gasta Más (por Categoría)",
            ]
            for c in tok.by_category:
                lines_md.append(f"- **{c.name}**: {c.total_tokens:,} (`in {c.input_tokens:,}` / `out {c.output_tokens:,}`)")
            lines_md.append("\n### Top Tools")
            for c in tok.by_tool[:15]:
                lines_md.append(f"- `{c.name}` ({c.calls} calls): {c.total_tokens:,} (`in {c.input_tokens:,}` / `out {c.output_tokens:,}`)")
            return "Monitor de Tokens", "\n".join(lines_md), True

        out = Text()
        for ev in self.events:
            out.append_text(format_live_event(ev))
            out.append("\n")
        return "Actividad en Tiempo Real", out or Text("(sin eventos)"), False

    def action_toggle_zoom(self) -> None:
        title, content, is_md = self._zoom_payload()
        self.push_screen(ZoomScreen(title, content, is_markdown=is_md))

    def action_switch_tab(self, tab_id: str) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        if tabs.active != tab_id:
            # Clear focus inside the outgoing pane so Textual does not bounce back when hiding it.
            self.set_focus(None)
            tabs.active = tab_id

    def action_refresh_now(self) -> None:
        self._refresh_worker(force_slow=True)
        self.notify("Snapshot actualizado", timeout=1.5)

    def action_focus_rag(self) -> None:
        self.action_switch_tab("tab-knowledge")
        self.query_one("#rag-input", Input).focus()

    def action_run_verify(self) -> None:
        self._start_aos_command("verify", ["verify"])

    def action_run_scan(self) -> None:
        self._start_aos_command("scan", ["scan", "--dry-run"])

    def action_run_sync(self) -> None:
        self._start_aos_command("sync", ["sync"])

    def action_run_refresh_cmd(self) -> None:
        self._start_aos_command("refresh", ["refresh"])

    @on(Button.Pressed)
    def handle_runner_buttons(self, event: Button.Pressed) -> None:
        mapping = {
            "btn-verify": ("verify", ["verify"]),
            "btn-scan": ("scan", ["scan", "--dry-run"]),
            "btn-sync": ("sync", ["sync"]),
            "btn-refresh-cmd": ("refresh", ["refresh"]),
            "btn-doctor": ("doctor", ["doctor"]),
        }
        if event.button.id in mapping:
            label, args = mapping[event.button.id]
            self._start_aos_command(label, args)

    @on(Input.Submitted, "#rag-input")
    def handle_rag_submit(self, event: Input.Submitted) -> None:
        self._rag_worker(event.value.strip())

    def _on_plan_row(self, row_key: Any) -> None:
        if not self.is_mounted or not self.screen_stack:
            return
        key = str(row_key.value)
        if key in self._doc_paths and key != self._selected_doc_key:
            self._selected_doc_key = key
            try:
                self._render_selected_doc()
            except NoMatches:
                pass

    @on(DataTable.RowSelected, "#plans-table")
    def handle_plan_selected(self, event: DataTable.RowSelected) -> None:
        self._on_plan_row(event.row_key)

    @on(DataTable.RowHighlighted, "#plans-table")
    def handle_plan_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._on_plan_row(event.row_key)

    def _on_session_row(self, row_key: Any) -> None:
        if not self.is_mounted or not self.screen_stack:
            return
        key = str(row_key.value)
        if key in self._sessions_by_key and key != self._selected_session_key:
            self._selected_session_key = key
            self._last_session_sig = None
            try:
                self._render_selected_session()
            except NoMatches:
                pass

    @on(DataTable.RowSelected, "#agents-sessions-table")
    def handle_session_selected(self, event: DataTable.RowSelected) -> None:
        self._on_session_row(event.row_key)

    @on(DataTable.RowHighlighted, "#agents-sessions-table")
    def handle_session_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._on_session_row(event.row_key)

    def _on_task_row(self, row_key: Any) -> None:
        if not self.is_mounted or not self.screen_stack:
            return
        key = str(row_key.value)
        if key in self._tasks_by_key and key != self._selected_task_key:
            self._selected_task_key = key
            self._last_task_tail_sig = None
            try:
                self._render_selected_task()
            except NoMatches:
                pass

    @on(DataTable.RowSelected, "#agents-tasks-table")
    def handle_task_selected(self, event: DataTable.RowSelected) -> None:
        self._on_task_row(event.row_key)

    @on(DataTable.RowHighlighted, "#agents-tasks-table")
    def handle_task_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._on_task_row(event.row_key)

    def _on_git_row(self, row_key: Any) -> None:
        if not self.is_mounted or not self.screen_stack:
            return
        path = str(row_key.value)
        if path != self._selected_git_path and self.snapshot and any(c.path == path for c in self.snapshot.git.changes):
            self._selected_git_path = path
            self._last_diff_sig = None
            self._diff_worker(path)

    @on(DataTable.RowSelected, "#git-files-table")
    def handle_git_file_selected(self, event: DataTable.RowSelected) -> None:
        self._on_git_row(event.row_key)

    @on(DataTable.RowHighlighted, "#git-files-table")
    def handle_git_file_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._on_git_row(event.row_key)

    @work(thread=True, exclusive=True, group="telemetry")
    def _refresh_worker(self, force_slow: bool = False) -> None:
        self._refreshing = True
        try:
            now = time.time()
            run_slow = force_slow or self.snapshot is None or (now - self._last_slow_check_ts) >= _SLOW_CHECK_INTERVAL_SECONDS
            snap = collect_telemetry(
                self.project_root,
                claude_home=self.claude_home,
                antigravity_home=self.antigravity_home,
                prev_snapshot=self.snapshot,
                include_slow=run_slow,
            )
            if run_slow:
                self._last_slow_check_ts = now
            self.call_from_thread(self._apply_snapshot, snap)
        except Exception as exc:
            self.call_from_thread(
                self._push_event,
                LiveEvent(
                    timestamp=time.strftime("%H:%M:%S"),
                    level="error",
                    source="telemetry",
                    message=str(exc),
                ),
            )
        finally:
            self._refreshing = False

    def _push_event(self, ev: LiveEvent) -> None:
        self.events.append(ev)
        self.events = self.events[-120:]
        if not self.is_mounted or not self.screen_stack:
            return
        try:
            feed = self._main_query("#live-feed-log", RichLog)
            feed.write(format_live_event(ev))
        except NoMatches:
            pass

    def _apply_snapshot(self, snap: TelemetrySnapshot) -> None:
        if not self.is_mounted or not self.screen_stack:
            return
        prev = self.snapshot
        new_events = diff_snapshots(prev, snap)
        self.snapshot = snap

        self._pulse_history.append(len(new_events))
        self._pulse_history = self._pulse_history[-30:]

        for ev in new_events:
            self._push_event(ev)

        try:
            self._update_header(snap)
            self._update_overview(snap)
            self._update_plans_tab(snap)
            self._update_agents_tab(snap)
            self._update_git_tab(snap)
            self._update_knowledge_tab(snap)
            self._update_tokens_tab(snap)
        except NoMatches:
            return
        if not self._rag_initialized:
            self._rag_initialized = True
            self._rag_worker("")

    def _update_header(self, snap: TelemetrySnapshot) -> None:
        box_w = self._main_query("#top-project").size.width
        val_max = max(16, box_w - 17) if box_w > 0 else 40

        def _clip_left(text: str, limit: int) -> str:
            if len(text) <= limit:
                return text
            return "…" + text[-(max(4, limit - 1)):]

        def _clip_right(text: str, limit: int) -> str:
            if len(text) <= limit:
                return text
            return text[: max(4, limit - 1)] + "…"

        ts_str = time.strftime("%H:%M:%S", time.localtime(snap.timestamp))
        info = Text(no_wrap=True, overflow="ellipsis")

        info.append("   AOS version:  ", style="#64748b")
        info.append(VERSION, style="bold #f8fafc")
        if self._paused:
            info.append("  || PAUSADO", style="bold #fbbf24")
        elif self._runner_busy:
            info.append("  ▸ [runner]", style="bold #fbbf24")
        info.append(f"  ·  {ts_str}\n", style="#94a3b8")

        info.append("Working folder:  ", style="#64748b")
        info.append(_clip_left(str(snap.project_root), val_max) + "\n", style="#e2e8f0")

        info.append("    Git branch:  ", style="#64748b")
        if snap.git.available:
            info.append(_clip_right(snap.git.branch, val_max) + "\n", style="bold #34d399")
        else:
            info.append("(sin git)\n", style="#64748b")

        info.append("   Active plan:  ", style="#64748b")
        if snap.status_report.plan:
            p = snap.status_report.plan
            plan_txt = f"{p.path.name} ({p.done}/{p.total})"
            info.append(_clip_right(plan_txt, val_max), style="#8aa8cc")
        else:
            info.append("(ninguno)", style="#64748b")

        self._main_query("#top-project", Static).update(info)

    def _card_inner_width(self, selector: str) -> int:
        w = self._main_query(selector).size.width
        return max(18, w - 4) if w > 0 else 28

    def _update_overview(self, snap: TelemetrySnapshot) -> None:
        self._main_query("#kpi-plan", Static).update(format_kpi_plan(snap, self._card_inner_width("#kpi-plan")))
        self._main_query("#kpi-agents", Static).update(format_kpi_agents(snap, self._card_inner_width("#kpi-agents")))
        self._main_query("#kpi-git", Static).update(format_kpi_git(snap, self._card_inner_width("#kpi-git")))
        self._main_query("#kpi-health", Static).update(format_kpi_health(snap, self._card_inner_width("#kpi-health")))
        self._main_query("#dash-pulse-content", Static).update(
            format_pulse_and_distribution(
                snap,
                self._pulse_history,
                inner_width=self._card_inner_width("#dash-pulse-box"),
            )
        )

        phase_rows: List[Tuple[Optional[str], Sequence[Any]]] = []
        if snap.active_plans:
            plan = snap.active_plans[0]
            self._main_query("#dash-phases-box").border_title = f"Plan Activo · {plan.path.name} ({plan.done}/{plan.total})"
            found_next = False
            for idx, ph in enumerate(plan.phases):
                if ph.done:
                    badge = Text("✓ DONE ", style="bold #34d399")
                    label = Text(ph.text, style="#94a3b8")
                elif not found_next:
                    found_next = True
                    badge = Text("▸ NEXT ", style="bold #fbbf24")
                    label = Text(ph.text, style="bold #f8fafc")
                else:
                    badge = Text("○ WAIT ", style="#64748b")
                    label = Text(ph.text, style="#cbd5e1")
                phase_rows.append((f"ph-{idx}", (badge, label)))
        else:
            self._main_query("#dash-phases-box").border_title = "Plan Activo (ninguno)"
            phase_rows.append((None, (Text("·", style="#64748b"), Text("No hay planes activos en .aos/plans/active/", style="#94a3b8"))))
        self._sync_table("#dash-phases-table", phase_rows)

        agent_rows: List[Tuple[Optional[str], Sequence[Any]]] = []
        combined_tasks = list(self._runner_jobs) + list(snap.tasks)
        for sess in snap.sessions[:6]:
            agent_rows.append((
                f"s:{sess.tool}:{sess.session_id}",
                (
                    agent_badge(sess.tool),
                    " ".join(sess.title.split())[:30],
                    status_text(sess.status),
                    compact_age(sess.updated_at),
                ),
            ))
        for idx, task in enumerate(combined_tasks[:6]):
            agent_rows.append((
                f"t:{task.agent}:{task.session_id}:{task.id}:{idx}",
                (
                    agent_badge(task.agent),
                    Text(re.sub(r"\.log$", "", task.title or task.id)[:30], style="#94a3b8"),
                    status_text(task.status),
                    compact_age(task.updated_at),
                ),
            ))
        if not agent_rows:
            agent_rows.append((None, (Text("·", style="#64748b"), "Sin sesiones o tasks activas detectadas", "-", "-")))
        self._sync_table("#dash-agents-table", agent_rows)

    def _update_plans_tab(self, snap: TelemetrySnapshot) -> None:
        prev_key = self._selected_doc_key
        self._doc_paths.clear()
        rows: List[Tuple[Optional[str], Sequence[Any]]] = []

        def _short(name: str) -> str:
            return name if len(name) <= 22 else name[:21] + "…"

        for p in snap.active_plans:
            key = f"plan:{p.path.name}"
            self._doc_paths[key] = p.path
            rows.append((key, (Text("PLAN", style="bold #fbbf24"), _short(p.path.name), f"{p.done}/{p.total}")))
        for spec in snap.specs:
            key = f"spec:{spec.path.name}"
            self._doc_paths[key] = spec.path
            rows.append((key, (Text(spec.kind.upper(), style="bold #38bdf8"), _short(spec.path.name), spec.status)))
        for adr in snap.adrs:
            key = f"adr:{adr.name}"
            self._doc_paths[key] = adr
            rows.append((key, (Text("ADR", style="bold #a78bfa"), _short(adr.name), "vigente")))
        for arch in snap.archived_plans[:15]:
            key = f"arch:{arch.name}"
            self._doc_paths[key] = arch
            rows.append((key, (Text("ARCH", style="#64748b"), _short(arch.name), "archivo")))

        if prev_key and prev_key in self._doc_paths:
            self._selected_doc_key = prev_key
        elif self._doc_paths:
            self._selected_doc_key = next(iter(self._doc_paths))

        self._sync_table("#plans-table", rows, preserve_key=self._selected_doc_key)
        self._render_selected_doc()

    def _render_selected_doc(self) -> None:
        if not self._selected_doc_key or self._selected_doc_key not in self._doc_paths:
            return
        path = self._doc_paths[self._selected_doc_key]
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            content = f"No se pudo leer `{path}`: {exc}"
        if content.startswith("---"):
            parts = content.split("\n---", 1)
            if len(parts) == 2:
                content = parts[1].lstrip("\r\n")

        sig = (str(path), hash(content))
        if sig == self._last_doc_sig:
            return
        self._last_doc_sig = sig

        try:
            rel_path = str(path.relative_to(self.project_root)).replace("\\", "/")
        except ValueError:
            rel_path = str(path)

        summary = Text(no_wrap=True, overflow="ellipsis")
        summary.append(path.name, style="bold #8aa8cc")
        summary.append("  ·  ", style="#475569")
        summary.append(rel_path, style="#94a3b8")
        self._main_query("#plans-summary-bar", Static).update(summary)
        self._main_query("#plans-markdown", Markdown).update(content)

    def _update_agents_tab(self, snap: TelemetrySnapshot) -> None:
        self._sessions_by_key.clear()
        sess_rows: List[Tuple[Optional[str], Sequence[Any]]] = []
        for sess in snap.sessions:
            skey = f"{sess.tool}:{sess.session_id}"
            self._sessions_by_key[skey] = sess
            sess_rows.append((
                skey,
                (
                    agent_badge(sess.tool),
                    Text(" ".join(sess.title.split())[:30], style="#e2e8f0"),
                    status_text(sess.status),
                    Text(compact_age(sess.updated_at), style="#94a3b8"),
                ),
            ))
        if not sess_rows:
            sess_rows.append((None, ("-", "Sin sesiones locales para este repo", "-", "-")))

        if self._selected_session_key not in self._sessions_by_key:
            self._selected_session_key = next(iter(self._sessions_by_key), None)
        self._sync_table("#agents-sessions-table", sess_rows, preserve_key=self._selected_session_key)
        self._render_selected_session()

        self._tasks_by_key.clear()
        task_rows: List[Tuple[Optional[str], Sequence[Any]]] = []
        all_tasks = list(self._runner_jobs) + list(snap.tasks)
        for idx, task in enumerate(all_tasks):
            tkey = f"{task.agent}:{task.session_id}:{task.id}"
            if tkey in self._tasks_by_key:
                tkey = f"{tkey}:{idx}"
            self._tasks_by_key[tkey] = task
            label = Text(re.sub(r"\.log$", "", task.title or task.id)[:24], style="#e2e8f0")
            if task.session_id and task.agent != "tui-runner":
                label.append(f"  {task.session_id[:6]}", style="#475569")
            task_rows.append((
                tkey,
                (
                    agent_badge(task.agent),
                    label,
                    status_text(task.status),
                    Text(compact_age(task.updated_at), style="#94a3b8"),
                ),
            ))
        if not task_rows:
            task_rows.append((None, ("-", "Sin tasks en background", "-", "-")))

        if self._selected_task_key not in self._tasks_by_key:
            self._selected_task_key = next(iter(self._tasks_by_key), None)
        self._sync_table("#agents-tasks-table", task_rows, preserve_key=self._selected_task_key)
        self._render_selected_task()

    def _render_selected_session(self) -> None:
        sess = self._sessions_by_key.get(self._selected_session_key or "")
        sig = (
            sess.tool,
            sess.session_id,
            sess.status,
            len(sess.activities),
            sess.activities[-1].summary if sess.activities else "",
        ) if sess else None
        if sig == self._last_session_sig:
            return
        self._last_session_sig = sig

        self._main_query("#agents-session-summary", Static).update(format_session_detail_summary(sess))
        log = self._main_query("#agents-activity-log", RichLog)
        log.clear()
        if not sess:
            return
        if not sess.activities:
            log.write(Text("Sin eventos recientes en el transcript.", style="#64748b"))
            return
        for item in sess.activities:
            log.write(format_activity_row(item))

    def _render_selected_task(self) -> None:
        task = self._tasks_by_key.get(self._selected_task_key or "")
        box = self._main_query("#agents-log-box")
        log = self._main_query("#agents-task-log", RichLog)
        if not task:
            box.border_title = "Tail de Log en Vivo"
            if self._last_task_tail_sig is not None:
                log.clear()
                self._last_task_tail_sig = None
            return
        lines = list(task.tail_lines)
        sig = (task.agent, task.session_id, task.id, task.status, len(lines), lines[-1] if lines else "")
        if sig == self._last_task_tail_sig:
            return
        self._last_task_tail_sig = sig
        box.border_title = f"Log · {task.agent}:{task.id} ({task.status})"
        log.clear()
        for line in lines:
            log.write(format_output_line(line))

    def _update_git_tab(self, snap: TelemetrySnapshot) -> None:
        git_rows: List[Tuple[Optional[str], Sequence[Any]]] = []
        if not snap.git.available:
            git_rows.append((None, ("-", "No es un repositorio Git")))
        elif not snap.git.changes:
            git_rows.append((None, (Text("✓", style="bold #34d399"), "Árbol de trabajo limpio")))
        else:
            for ch in snap.git.changes:
                code_str = ch.code.strip() or "?"
                color = "#34d399" if "?" in code_str or "A" in code_str else ("#f87171" if "D" in code_str else "#fbbf24")
                git_rows.append((ch.path, (Text(code_str, style=f"bold {color}"), ch.path)))

        valid_paths = {ch.path for ch in snap.git.changes}
        if self._selected_git_path not in valid_paths:
            self._selected_git_path = snap.git.changes[0].path if snap.git.changes else None
            self._last_diff_sig = None

        self._sync_table("#git-files-table", git_rows, preserve_key=self._selected_git_path)

        commits_log = self._main_query("#git-commits-log", RichLog)
        commits_log.clear()
        for c in snap.git.recent_commits:
            commits_log.write(Text(c, style="#cbd5e1"))

        if self._selected_git_path:
            self._diff_worker(self._selected_git_path)
        else:
            diff_log = self._main_query("#git-diff-log", RichLog)
            diff_log.clear()
            diff_log.write(Text("Sin cambios pendientes para mostrar.", style="#64748b"))

    @work(thread=True, exclusive=True, group="git-diff")
    def _diff_worker(self, rel_path: str) -> None:
        diff_text = read_git_file_diff(self.project_root, rel_path)
        self.call_from_thread(self._apply_git_diff, rel_path, diff_text)

    def _apply_git_diff(self, rel_path: str, diff_text: str) -> None:
        if not self.is_mounted or not self.screen_stack:
            return
        sig = (rel_path, hash(diff_text))
        if sig == self._last_diff_sig:
            return
        self._last_diff_sig = sig
        try:
            self._main_query("#git-diff-box").border_title = f"Diff · {rel_path}"
            diff_log = self._main_query("#git-diff-log", RichLog)
            diff_log.clear()
            md_path = self.project_root / rel_path
            if md_path.suffix.lower() == ".md" and md_path.is_file():
                doc = md_path.read_text(encoding="utf-8", errors="replace")
                diff_log.write(RichMarkdown(markdown_diff(diff_text, doc)), expand=True)
                return
            for line_text in format_diff_lines(diff_text):
                diff_log.write(line_text)
        except NoMatches:
            pass

    def _update_knowledge_tab(self, snap: TelemetrySnapshot) -> None:
        gotcha_rows: List[Tuple[Optional[str], Sequence[Any]]] = []
        for idx, g in enumerate(snap.gotchas):
            gotcha_rows.append((f"g:{g['filename']}:{idx}", (severity_text(g["severity"]), g["title"], g["date"])))
        if not gotcha_rows:
            gotcha_rows.append((None, ("-", "Sin gotchas registrados", "-")))
        self._sync_table("#gotchas-table", gotcha_rows)

        doctor_rows: List[Tuple[Optional[str], Sequence[Any]]] = []
        for idx, f in enumerate(snap.doctor_findings):
            doctor_rows.append((f"d:{idx}", (level_text(f.level), f.area, f.message)))
        if not doctor_rows:
            doctor_rows.append((None, (Text("OK", style="bold #34d399"), "harness", "0 hallazgos")))
        self._sync_table("#doctor-table", doctor_rows)

        native_log = self._main_query("#native-log", RichLog)
        native_log.clear()
        for tool, state in snap.native_tools.items():
            color = "#34d399" if "día" in state.lower() else "#fbbf24"
            native_log.write(Text(f"• {tool}: {state}", style=color))
        if snap.missing_deps:
            native_log.write(Text("\nDependencias opcionales faltantes:", style="bold #fbbf24"))
            for name, hint in snap.missing_deps:
                native_log.write(Text(f"  - {name}: {hint}", style="#94a3b8"))
        if snap.lessons:
            native_log.write(Text("\nLecciones recientes (LEDGER):", style="bold #a78bfa"))
            for lesson in snap.lessons[:5]:
                native_log.write(Text(f"  - {lesson}", style="#cbd5e1"))

    def _update_tokens_tab(self, snap: TelemetrySnapshot) -> None:
        self._main_query("#kpi-tok-in", Static).update(format_kpi_tok_input(snap, self._card_inner_width("#kpi-tok-in")))
        self._main_query("#kpi-tok-cache", Static).update(format_kpi_tok_cache(snap, self._card_inner_width("#kpi-tok-cache")))
        self._main_query("#kpi-tok-out", Static).update(format_kpi_tok_output(snap, self._card_inner_width("#kpi-tok-out")))
        self._main_query("#kpi-tok-ctx", Static).update(format_kpi_tok_context(snap, self._card_inner_width("#kpi-tok-ctx")))

        tok = snap.tokens
        total_billable = max(1, tok.input_tokens + tok.output_tokens)

        cat_rows: List[Tuple[Optional[str], Sequence[Any]]] = []
        for c in tok.by_category:
            pct = int(round((c.total_tokens / total_billable) * 100)) if (tok.input_tokens + tok.output_tokens) else 0
            cat_rows.append((
                f"cat:{c.name}",
                (
                    Text(c.name, style="bold #f8fafc"),
                    format_tokens_compact(c.input_tokens),
                    format_tokens_compact(c.output_tokens),
                    Text(format_tokens_compact(c.total_tokens), style="bold #8aa8cc"),
                    f"{pct}%",
                    token_bar(c.total_tokens, total_billable, width=10),
                ),
            ))
        if not cat_rows:
            cat_rows.append((None, ("Sin datos de tokens", "-", "-", "-", "-", "-")))
        self._sync_table("#tokens-cat-table", cat_rows)

        tool_rows: List[Tuple[Optional[str], Sequence[Any]]] = []
        for idx, c in enumerate(tok.by_tool[:25]):
            pct = int(round((c.total_tokens / total_billable) * 100)) if (tok.input_tokens + tok.output_tokens) else 0
            tool_rows.append((
                f"tool:{c.name}:{idx}",
                (
                    Text(c.name, style="bold #8aa8cc"),
                    str(c.calls),
                    format_tokens_compact(c.input_tokens),
                    format_tokens_compact(c.output_tokens),
                    f"{pct}%",
                    token_bar(c.total_tokens, total_billable, width=8, color="#a78bfa"),
                ),
            ))
        if not tool_rows:
            tool_rows.append((None, ("Sin tools registradas", "-", "-", "-", "-", "-")))
        self._sync_table("#tokens-tools-table", tool_rows)

        sess_rows: List[Tuple[Optional[str], Sequence[Any]]] = []
        for idx, s in enumerate(tok.by_session[:20]):
            cost_s = f"${s.cost_usd:.2f}" if s.cost_usd > 0 else "-"
            sess_rows.append((
                f"tsess:{s.tool}:{s.session_id}:{idx}",
                (
                    agent_badge(s.tool),
                    " ".join(s.title.split())[:22],
                    format_tokens_compact(s.input_tokens),
                    format_tokens_compact(s.cache_read_tokens),
                    format_tokens_compact(s.output_tokens),
                    format_tokens_compact(s.context_window_tokens),
                    cost_s,
                ),
            ))
        if not sess_rows:
            sess_rows.append((None, ("-", "Sin sesiones con tokens", "-", "-", "-", "-", "-")))
        self._sync_table("#tokens-sessions-table", sess_rows)

        harness_rows: List[Tuple[Optional[str], Sequence[Any]]] = []
        for idx, w in enumerate(tok.harness_weights):
            cls_color = "#fbbf24" if w.cost_class == "always-on" else ("#8aa8cc" if w.cost_class == "on-demand" else "#94a3b8")
            harness_rows.append((
                f"hw:{idx}",
                (
                    w.area,
                    Text(w.cost_class, style=cls_color),
                    str(w.files),
                    Text(format_tokens_compact(w.est_tokens), style="bold #f8fafc"),
                ),
            ))
        if not harness_rows:
            harness_rows.append((None, ("Sin artefactos .aos/", "-", "-", "-")))
        self._sync_table("#tokens-harness-table", harness_rows)

    @work(thread=True, exclusive=True, group="rag")
    def _rag_worker(self, query: str) -> None:
        try:
            res = search_context(self.project_root, query=query or None, limit=12)
            self._rag_last = res
            self.call_from_thread(self._apply_rag_results, res.mode, res.query, res.results, res.note)
        except Exception as exc:
            self.call_from_thread(self._apply_rag_error, str(exc))

    def _apply_rag_results(self, mode: str, query: str, hits: list, note: str) -> None:
        if not self.is_mounted or not self.screen_stack:
            return
        try:
            self._main_query("#rag-mode-badge", Static).update(f"RAG: {mode}")
        except NoMatches:
            return
        rows: List[Tuple[Optional[str], Sequence[Any]]] = []
        for idx, hit in enumerate(hits):
            rows.append((
                f"rag:{idx}",
                (
                    kind_text(hit.kind),
                    f"{hit.score:.2f}",
                    f"{hit.title} › {hit.section}",
                ),
            ))
        if not rows:
            rows.append((None, ("-", "-", note or f"Sin resultados para '{query}'")))
        self._sync_table("#rag-results-table", rows)

    def _apply_rag_error(self, message: str) -> None:
        if not self.is_mounted or not self.screen_stack:
            return
        try:
            self._main_query("#rag-mode-badge", Static).update("RAG: error")
            self._sync_table("#rag-results-table", [(None, (Text("ERR", style="bold #f87171"), "-", message))])
        except NoMatches:
            pass

    def _start_aos_command(self, label: str, aos_args: List[str]) -> None:
        if self._runner_busy:
            self.notify("Ya hay un comando ejecutándose en Consola.", severity="warning", timeout=2.0)
            return
        self.action_switch_tab("tab-console")
        self._runner_busy = True
        self._run_aos_worker(label, aos_args)

    @work(thread=True, exclusive=True, group="runner")
    def _run_aos_worker(self, label: str, aos_args: List[str]) -> None:
        cmd = [sys.executable, "-m", "dass_aos", *aos_args]
        cmd_str = f"aos {' '.join(aos_args)}"
        started = time.time()
        job = AgentTaskInfo(
            id=f"{label}-{int(started)}",
            agent="tui-runner",
            status="running",
            title=cmd_str,
            updated_at=started,
            tail_lines=[],
        )

        def _begin() -> None:
            self._runner_jobs.insert(0, job)
            self._runner_jobs = self._runner_jobs[:10]
            if not self.is_mounted or not self.screen_stack:
                return
            try:
                self._main_query("#runner-status-bar", Static).update(
                    f"[bold #fbbf24]▸ EJECUTANDO[/]  {cmd_str}"
                )
                rlog = self._main_query("#runner-log", RichLog)
                rlog.clear()
                rlog.write(Text(f"$ {cmd_str}\n", style="bold #38bdf8"))
            except NoMatches:
                pass
            self._push_event(LiveEvent(time.strftime("%H:%M:%S"), "info", "runner", f"Iniciado: {cmd_str}"))

        self.call_from_thread(_begin)

        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"  # keep our prints in order with child tool output

        exit_code = 1
        try:
            with subprocess.Popen(
                cmd,
                cwd=str(self.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            ) as proc:
                self._active_proc = proc
                if proc.stdout is not None:
                    for line in proc.stdout:
                        clean = line.rstrip("\r\n")
                        self.call_from_thread(self._append_runner_line, job, clean)
                exit_code = proc.wait()
        except Exception as exc:
            err_line = f"[runner error] {exc}"
            self.call_from_thread(self._append_runner_line, job, err_line)
            exit_code = 1
        finally:
            self._active_proc = None
            elapsed = time.time() - started
            try:
                self.call_from_thread(self._finish_runner, job, cmd_str, exit_code, elapsed)
            except RuntimeError:
                # App event loop already closed during shutdown.
                self._runner_busy = False

    def _append_runner_line(self, job: AgentTaskInfo, line: str) -> None:
        job.tail_lines.append(line)
        if len(job.tail_lines) > 200:
            job.tail_lines = job.tail_lines[-200:]
        job.updated_at = time.time()
        if not self.is_mounted or not self.screen_stack:
            return
        try:
            self._main_query("#runner-log", RichLog).write(format_output_line(line))
        except NoMatches:
            pass

    def _finish_runner(self, job: AgentTaskInfo, cmd_str: str, exit_code: int, elapsed: float) -> None:
        job.status = "finished" if exit_code == 0 else "failed"
        job.updated_at = time.time()
        self._runner_busy = False
        if exit_code == 0:
            banner = f"[bold #34d399]✓ PASSED[/]  {cmd_str}  [dim]({elapsed:.1f}s · código 0)[/]"
            self._push_event(LiveEvent(time.strftime("%H:%M:%S"), "success", "runner", f"OK ({elapsed:.1f}s): {cmd_str}"))
            if self.is_mounted:
                self.notify(f"✓ {cmd_str} ({elapsed:.1f}s)", timeout=2.5)
        else:
            banner = f"[bold #f87171]✖ FAILED[/]  {cmd_str}  [dim]({elapsed:.1f}s · código {exit_code})[/]"
            self._push_event(LiveEvent(time.strftime("%H:%M:%S"), "error", "runner", f"Falló ({exit_code}): {cmd_str}"))
            if self.is_mounted:
                self.notify(f"✖ {cmd_str} falló ({exit_code})", severity="error", timeout=3.5)
        if self.is_mounted and self.screen_stack:
            try:
                self._main_query("#runner-status-bar", Static).update(banner)
            except NoMatches:
                pass
            self._refresh_worker(force_slow=True)
