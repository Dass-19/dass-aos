"""Textual TUI application for DASS-AOS (`aos tui`)."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

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
    AgentActivityItem,
    AgentSessionInfo,
    AgentTaskInfo,
    LiveEvent,
    TelemetrySnapshot,
    collect_telemetry,
    diff_snapshots,
    read_git_file_diff,
)
from .controller import AlertDispatcher, SessionController
from .pty_terminal import AgentTerminalWidget, PtySession, detect_terminal_agent_state
from .widgets import (
    brand_lockup,
    agent_badge,
    compact_age,
    diff_stats,
    format_activity_row,
    format_diff_lines,
    format_git_commit_line,
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
    format_lesson_detail,
    format_live_event,
    format_pulse_and_distribution,
    format_session_detail_summary,
    format_subagent_graph,
    format_task_log_header,
    format_task_time_compact,
    format_tokens_compact,
    parse_lesson_entry,
    token_bar,
)

_SLOW_CHECK_INTERVAL_SECONDS = 10.0
_IDLE_GIT_INTERVAL_SECONDS = 5.0
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
                "### Control en Vivo y Sesiones (estilo Herdr)\n"
                "- `Espacio` — Pausar / reanudar el refresco automático en tiempo real\n"
                "- `z` — Maximizar (zoom) el panel activo (`Esc` para salir); dentro del PTY usa `Ctrl+Z` (o `F10`) directo sin `Ctrl+G`\n"
                "- `g` — Ver Grafo de Subagentes e interacciones en vivo (en pestaña 3 · Agentes)\n"
                "- `m` — Silenciar / activar alertas sonoras y notificaciones del SO (`PENDING`)\n"
                "- `n` — Crear nueva sesión con nombre (en pestaña 3 · Agentes)\n"
                "- `k` — Detener sesión/proceso activo (en pestaña 3 · Agentes)\n"
                "- `Esc` — Cortar locución de voz (TTS) en curso\n"
                "- `r` — Forzar refresco completo (incluye `aos doctor`)\n"
                "- `t` — Cambiar tema visual (`Cyan` · `Emerald` · `Violet`)\n\n"
                "### Acciones del Motor\n"
                "- `v` `aos verify` · `s` `aos scan --dry-run` · `u` `aos update` · `y` `aos sync`\n"
                "- `q` — Salir de la TUI (pulsa `Esc` o `?` para cerrar esta ventana)"
            )
            yield Markdown(help_md)


class ZoomScreen(ModalScreen[Optional[str]]):
    """Fullscreen reader or interactive PTY modal (`z`) for logs, diffs, docs, or live CLI terminals."""

    BINDINGS = [
        Binding("escape", "dismiss", "Cerrar"),
        Binding("z", "dismiss", "Cerrar"),
        Binding("ctrl+z", "dismiss", "Cerrar"),
        Binding("alt+z", "dismiss", "Cerrar"),
        Binding("f10", "dismiss", "Cerrar"),
        Binding("q", "dismiss", "Cerrar"),
    ]

    def __init__(
        self,
        title: str,
        content: Any,
        is_markdown: bool = False,
        pty_session: Optional[PtySession] = None,
    ) -> None:
        super().__init__()
        self._zoom_title = title
        self._zoom_content = content
        self._is_markdown = is_markdown
        self._pty_session = pty_session

    def compose(self) -> ComposeResult:
        box = Vertical(id="zoom-dialog")
        if self._pty_session is not None:
            box.border_title = f"{self._zoom_title}  (PTY Interactivo · rueda/PgUp scroll · Ctrl+Z volver al CLI · Ctrl+G Navegación)"
        else:
            box.border_title = f"{self._zoom_title}  (Esc / z para volver)"
        with box:
            if self._pty_session is not None:
                yield AgentTerminalWidget("", id="zoom-terminal-pane")
            else:
                with VerticalScroll(id="zoom-scroll"):
                    if self._is_markdown:
                        yield Markdown(str(self._zoom_content))
                    else:
                        yield Static(self._zoom_content)

    def on_mount(self) -> None:
        if self._pty_session is not None:
            try:
                term = self.query_one("#zoom-terminal-pane", AgentTerminalWidget)
                term.attach_pty(self._pty_session)
                term.focus()
                self.call_after_refresh(lambda: term.refresh_viewport(force=True))
            except NoMatches:
                pass


class NewSessionScreen(ModalScreen[Optional[Tuple[str, str]]]):
    """Compact modal to create a named agent session without overloading the prompt input."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancelar"),
    ]

    def __init__(self, default_tool: str = "claude-code", default_name: str = "") -> None:
        super().__init__()
        self._tool = default_tool if default_tool in ("claude-code", "antigravity") else "claude-code"
        self._default_name = default_name

    def compose(self) -> ComposeResult:
        box = Vertical(id="new-session-dialog")
        box.border_title = "Nueva Sesión de Agente"
        with box:
            yield Static("Herramienta:", classes="modal-label")
            with Horizontal(id="new-session-tools"):
                yield Button(
                    "CC · Claude Code",
                    id="btn-new-tool-cc",
                    classes="view-pill -active" if self._tool == "claude-code" else "view-pill",
                )
                yield Button(
                    "AG · Antigravity",
                    id="btn-new-tool-ag",
                    classes="view-pill -active" if self._tool == "antigravity" else "view-pill",
                )
            yield Static("Nombre de la sesión:", classes="modal-label")
            yield Input(
                value=self._default_name,
                placeholder="ej. refactor-auth (Enter para crear)",
                id="new-session-name-input",
            )
            with Horizontal(id="new-session-actions"):
                yield Button("Crear", id="btn-new-session-ok")
                yield Button("Cancelar", id="btn-new-session-cancel")

    def on_mount(self) -> None:
        try:
            self.query_one("#new-session-name-input", Input).focus()
        except NoMatches:
            pass

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _select_tool(self, tool: str) -> None:
        self._tool = tool
        try:
            self.query_one("#btn-new-tool-cc", Button).set_class(tool == "claude-code", "-active")
            self.query_one("#btn-new-tool-ag", Button).set_class(tool == "antigravity", "-active")
        except NoMatches:
            pass

    def _submit(self) -> None:
        try:
            name = self.query_one("#new-session-name-input", Input).value.strip()
        except NoMatches:
            name = self._default_name
        self.dismiss((self._tool, name))

    @on(Input.Submitted, "#new-session-name-input")
    def handle_submit_input(self, _event: Input.Submitted) -> None:
        self._submit()

    @on(Button.Pressed)
    def handle_buttons(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-new-tool-cc":
            self._select_tool("claude-code")
        elif bid == "btn-new-tool-ag":
            self._select_tool("antigravity")
        elif bid == "btn-new-session-ok":
            self._submit()
        elif bid == "btn-new-session-cancel":
            self.dismiss(None)


class CliInstallScreen(ModalScreen[Optional[str]]):
    """Modal shown when the session's agent CLI (`claude` / `agy`) is not installed in PATH."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancelar"),
    ]

    def __init__(self, cli_info: Dict[str, Any]) -> None:
        super().__init__()
        self._info = cli_info

    def compose(self) -> ComposeResult:
        info = self._info
        box = Vertical(id="cli-install-dialog")
        box.border_title = f"CLI no instalado · {info['display_name']}"
        with box:
            msg = Text()
            msg.append("▲ No se encontró el comando ", style="bold #fbbf24")
            msg.append(f"`{info['binary']}`", style="bold #f8fafc")
            msg.append(" en tu PATH.\n\n", style="bold #fbbf24")
            msg.append("Comando de instalación:\n", style="bold #94a3b8")
            msg.append(f"  {info['install_display']}\n\n", style="bold #8aa8cc")
            msg.append("Importante (login requerido):\n", style="bold #d9b15f")
            msg.append(f"  {info['login_hint']}\n", style="#cbd5e1")
            msg.append(f"  Docs: {info['docs_url']}", style="#64748b")
            yield Static(msg, id="cli-install-body")
            with Horizontal(id="cli-install-actions"):
                yield Button("Instalar ahora", id="btn-cli-install")
                yield Button("Abrir Shell", id="btn-cli-shell")
                yield Button("Cancelar", id="btn-cli-cancel")

    def on_mount(self) -> None:
        try:
            self.query_one("#btn-cli-install", Button).focus()
        except NoMatches:
            pass

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed)
    def handle_buttons(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-cli-install":
            self.dismiss("install")
        elif bid == "btn-cli-shell":
            self.dismiss("shell")
        elif bid == "btn-cli-cancel":
            self.dismiss(None)


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
        Binding("ctrl+z", "toggle_zoom", "Zoom", show=False),
        Binding("alt+z", "toggle_zoom", "Zoom", show=False),
        Binding("f10", "toggle_zoom", "Zoom", show=False),
        Binding("g", "toggle_subagent_graph", "Grafo", show=True),
        Binding("m", "toggle_mute", "Mute", show=True),
        Binding("n", "new_agent_session", "Nueva", show=False),
        Binding("k", "stop_agent_session", "Stop", show=False),
        Binding("escape", "stop_voice", "Cortar Voz", show=False),
        Binding("r", "refresh_now", "Refrescar", show=True),
        Binding("v", "run_verify", "Verify", show=True),
        Binding("s", "run_scan", "Scan", show=True),
        Binding("u", "run_update", "Update", show=True),
        Binding("y", "run_sync", "Sync", show=False),
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
        self._last_git_check_ts = 0.0

        self._doc_paths: Dict[str, Path] = {}
        self._selected_doc_key: Optional[str] = None
        self._last_doc_sig: Optional[Tuple[str, int]] = None

        self._sessions_by_key: Dict[str, AgentSessionInfo] = {}
        self._selected_session_key: Optional[str] = None
        self._last_session_sig: Optional[tuple] = None

        self._tasks_by_key: Dict[str, AgentTaskInfo] = {}
        self._all_tasks: List[AgentTaskInfo] = []
        self._tasks_filter_mode: str = "session"
        self._selected_task_key: Optional[str] = None
        self._last_task_tail_sig: Optional[tuple] = None
        self._last_action_btn_sig: Optional[tuple] = None

        self._selected_git_path: Optional[str] = None
        self._last_diff_sig: Optional[tuple] = None

        self._table_sigs: Dict[str, List[Tuple[Optional[str], Tuple[str, ...]]]] = {}
        self._runner_jobs: List[AgentTaskInfo] = []
        self._active_proc: Optional[subprocess.Popen] = None
        self._rag_initialized = False
        self._rag_last: Any = None
        self._knowledge_mode: str = "rag"
        self._rag_hits_by_key: Dict[str, Any] = {}
        self._selected_rag_key: Optional[str] = None
        self._gotchas_by_key: Dict[str, Dict[str, str]] = {}
        self._selected_gotcha_key: Optional[str] = None
        self._doctor_by_key: Dict[str, Any] = {}
        self._selected_doctor_key: Optional[str] = None
        self._lessons_by_key: Dict[str, str] = {}
        self._selected_lesson_key: Optional[str] = None
        self._dirty_tabs: Set[str] = set()
        self._agent_right_mode: str = "terminal"
        self.alerts = AlertDispatcher(muted=False)
        cli_home_override = (
            (antigravity_home.parent / "antigravity-cli")
            if antigravity_home is not None
            else None
        )
        self.controller = SessionController(
            project_root=self.project_root,
            antigravity_cli_home=cli_home_override,
        )

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
                            with Horizontal(id="tasks-filter-bar"):
                                yield Button("Sesión (0)", id="btn-tasks-filter-session", classes="filter-pill -active")
                                yield Button("Todas (0)", id="btn-tasks-filter-all", classes="filter-pill")
                            yield DataTable(id="agents-tasks-table")
                    with Vertical(classes="col-right-wide"):
                        with Horizontal(id="agent-view-bar"):
                            yield Button("Terminal", id="btn-view-terminal", classes="view-pill -active")
                            yield Button("Timeline", id="btn-view-inspector", classes="view-pill")
                            yield Button("Grafo", id="btn-view-graph", classes="view-pill")
                            yield Button("Log", id="btn-view-log", classes="view-pill")
                            yield Static("", id="agent-view-spacer")
                            yield Button("⛶ Zoom", id="btn-agent-zoom", classes="view-action-pill")
                            yield Button("+ Nueva", id="btn-agent-new", classes="view-action-pill")
                        with Vertical(id="agents-activity-box", classes="panel"):
                            yield Static("", id="agents-session-summary")
                            yield AgentTerminalWidget("", id="agent-terminal-pane")
                            yield RichLog(id="agents-activity-log", wrap=True, markup=False)
                        with Vertical(id="agents-log-box", classes="panel"):
                            yield RichLog(id="agents-task-log", wrap=True, markup=False)
                        with Horizontal(id="agent-composer-row"):
                            yield Input(
                                placeholder="Enviar prompt a la sesión (Enter · /voice)...",
                                id="agent-prompt-input",
                            )
                            yield Button("CLI", id="btn-agent-attach")
                            yield Button("🎤 Voz", id="btn-agent-voice")
                            yield Button("Stop", id="btn-agent-stop")

            # 4. Git & Diff
            with TabPane("Git & Diff", id="tab-git"):
                with Horizontal(classes="split-h"):
                    with Vertical(classes="col-left-mid"):
                        with Vertical(id="git-files-box", classes="panel"):
                            yield DataTable(id="git-files-table")
                        with Vertical(id="git-commits-box", classes="panel"):
                            yield RichLog(id="git-commits-log", wrap=False, markup=False, auto_scroll=False)
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
                with Horizontal(id="knowledge-view-bar"):
                    yield Button("Memoria RAG (0)", id="btn-know-rag", classes="view-pill -active")
                    yield Button("Gotchas (0)", id="btn-know-gotchas", classes="view-pill")
                    yield Button("Salud & Nativos (0)", id="btn-know-health", classes="view-pill")
                    yield Button("Lecciones (0)", id="btn-know-lessons", classes="view-pill")
                with Horizontal(id="knowledge-grid"):
                    with Vertical(id="knowledge-left"):
                        with Vertical(id="rag-results-box", classes="panel"):
                            yield DataTable(id="rag-results-table")
                        with Vertical(id="gotchas-box", classes="panel"):
                            yield DataTable(id="gotchas-table")
                        with Vertical(id="doctor-box", classes="panel"):
                            yield DataTable(id="doctor-table")
                        with Vertical(id="lessons-box", classes="panel"):
                            yield DataTable(id="lessons-table")
                    with Vertical(id="knowledge-right"):
                        with Vertical(id="knowledge-detail-box", classes="panel"):
                            yield RichLog(id="knowledge-detail-log", wrap=True, markup=False, auto_scroll=False)

            # 6. Consola / Acciones
            with TabPane("Consola", id="tab-console"):
                with Horizontal(id="runner-toolbar"):
                    yield Button("Verify (v)", id="btn-verify")
                    yield Button("Scan (s)", id="btn-scan")
                    yield Button("Update (u)", id="btn-update")
                    yield Button("Doctor", id="btn-doctor")
                    yield Static("[dim]● Listo[/]", id="runner-status-bar")
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
        self._init_console_welcome()
        self._apply_agent_right_mode()
        self._apply_knowledge_mode()
        # Fast first paint (<100ms): defer heavy doctor/native checks by 150ms.
        self._refresh_worker(force_slow=False)
        self.set_timer(0.15, lambda: self._refresh_worker(force_slow=True))
        self.set_interval(self.interval, self._tick_refresh)
        self.set_interval(0.15, self._tick_pty)

    def _init_console_welcome(self) -> None:
        try:
            self._main_query("#runner-output-box").border_subtitle = "z Zoom"
            rlog = self._main_query("#runner-log", RichLog)
            intro = Text()
            intro.append("Comandos disponibles en DASS-AOS\n\n", style="bold #d9b15f")
            cmds = (
                ("Verify (v)", "aos verify", "#9aa59c", "Ejecuta linters y suite de tests configurados en .aos/config.json."),
                ("Scan (s)", "aos scan --dry-run", "#c46a6a", "Análisis estático de seguridad (Semgrep / Checkov)."),
                ("Update (u)", "aos update", "#d9b15f", "Migra .aos/, sincroniza instrucciones y actualiza adapt-native."),
                ("Doctor", "aos doctor", "#8aa8cc", "Audita salud del harness, reglas, hooks y dependencias."),
            )
            for label, cmd, color, desc in cmds:
                intro.append(f"  {label:<12} ", style=f"bold {color}")
                intro.append(f"{cmd:<20} ", style="bold #f8fafc")
                intro.append(f"{desc}\n", style="#94a3b8")
            intro.append("\nPulsa un botón arriba o su atajo de teclado para ver la salida en tiempo real.", style="#64748b")
            rlog.write(intro)
        except NoMatches:
            pass

    def on_unmount(self) -> None:
        self.controller.stop_active_process()
        self.controller.tts.stop()
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
            "#agents-sessions-box": "Sesiones",
            "#agents-tasks-box": "Tasks",
            "#agents-activity-box": "Terminal CLI (PTY)",
            "#agents-log-box": "Log de Task",
            "#git-files-box": "Cambios en Workspace (Git)",
            "#git-commits-box": "Commits Recientes",
            "#git-diff-box": "Diff del Archivo Seleccionado",
            "#rag-results-box": "Resultados RAG (aos context)",
            "#gotchas-box": "Gotchas Prioritarios",
            "#doctor-box": "Auditoría Harness (aos doctor)",
            "#lessons-box": "Lecciones (LEDGER.md)",
            "#knowledge-detail-box": "Detalle Técnico",
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
            ("#agents-tasks-table", ("", "Task", "Estado", "Hora")),
            ("#git-files-table", ("Flag", "Archivo")),
            ("#rag-results-table", ("Tipo", "Score", "Documento › Sección")),
            ("#gotchas-table", ("Gravedad", "Gotcha", "Fecha")),
            ("#doctor-table", ("Nivel", "Área", "Resumen")),
            ("#lessons-table", ("Fecha", "Lección")),
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

    def _tick_pty(self) -> None:
        if not self.is_mounted or not self.screen_stack:
            return
        self.controller.tts.poll()
        self._update_agent_action_buttons()
        if not self.controller.pty_sessions:
            return
        changed = self.controller.poll_all_ptys(self._sessions_by_key)
        closed_ptys = list(self.controller.recently_closed_ptys)
        self.controller.recently_closed_ptys.clear()
        closed_keys = {k for k, _ in closed_ptys}
        if closed_keys:
            if isinstance(self.screen, ZoomScreen):
                z_pty = self.screen._pty_session
                if z_pty is not None and z_pty.session_key in closed_keys:
                    self.screen.dismiss(None)
            try:
                term = self._main_query("#agent-terminal-pane", AgentTerminalWidget)
                if term.pty_session is not None and term.pty_session.session_key in closed_keys:
                    term.attach_pty(None)
                    if self.focused is term:
                        try:
                            self._main_query("#agents-sessions-table", DataTable).focus()
                        except NoMatches:
                            self.set_focus(None)
            except NoMatches:
                pass
            for ckey, _code in closed_ptys:
                csess = self._sessions_by_key.get(ckey)
                label = csess.title if csess is not None else ckey
                self.notify(f"Terminal cerrada (/exit): {label}", timeout=2.5)
            self._last_session_sig = None
            try:
                self._render_selected_session()
                self._update_agent_action_buttons()
            except NoMatches:
                pass
        newly_pending = self.alerts.process_sessions(list(self._sessions_by_key.values()))
        for psess in newly_pending:
            reason = psess.pending_reason or "Esperando acción en terminal"
            self.notify(f"⚠ PENDING ({psess.title}): {reason}", severity="warning", timeout=5.0)
        if changed:
            if isinstance(self.screen, ZoomScreen):
                try:
                    self.screen.query_one("#zoom-terminal-pane", AgentTerminalWidget).refresh_viewport()
                except NoMatches:
                    pass
            else:
                try:
                    term = self._main_query("#agent-terminal-pane", AgentTerminalWidget)
                    term.refresh_viewport()
                    self._render_selected_session()
                except NoMatches:
                    pass

    def _apply_agent_right_mode(self) -> None:
        try:
            term = self._main_query("#agent-terminal-pane", AgentTerminalWidget)
            act_log = self._main_query("#agents-activity-log", RichLog)
            box = self._main_query("#agents-activity-box")
            log_box = self._main_query("#agents-log-box")
            mode = self._agent_right_mode
            is_term = mode == "terminal"
            is_graph = mode == "graph"
            is_log = mode == "log"
            box.display = not is_log
            log_box.display = is_log
            term.display = is_term
            act_log.display = not is_term and not is_log
            if is_term:
                box.border_title = "Terminal CLI (PTY)"
                box.border_subtitle = "Enter conectar · Ctrl+Z Zoom · Ctrl+G salir"
            elif is_graph:
                box.border_title = "Grafo de Subagentes"
                box.border_subtitle = "g alternar · z Zoom"
            elif not is_log:
                box.border_title = "Timeline & Detalle"
                box.border_subtitle = "z Zoom"
            pill_map = {
                "#btn-view-terminal": "terminal",
                "#btn-view-inspector": "inspector",
                "#btn-view-graph": "graph",
                "#btn-view-log": "log",
            }
            for sel, target in pill_map.items():
                try:
                    self._main_query(sel, Button).set_class(mode == target, "-active")
                except NoMatches:
                    pass
            self._last_session_sig = None
            self._render_selected_session()
            if is_log:
                self._last_task_tail_sig = None
                self._render_selected_task()
            self._update_agent_action_buttons()
            term.refresh_viewport()
        except NoMatches:
            pass

    def _set_agent_right_mode(self, mode: str) -> None:
        if mode not in ("terminal", "inspector", "graph", "log"):
            return
        self._agent_right_mode = mode
        self._apply_agent_right_mode()

    def _set_tasks_filter(self, mode: str) -> None:
        if mode not in ("session", "all"):
            return
        self._tasks_filter_mode = mode
        try:
            self._main_query("#btn-tasks-filter-session", Button).set_class(mode == "session", "-active")
            self._main_query("#btn-tasks-filter-all", Button).set_class(mode == "all", "-active")
        except NoMatches:
            pass
        self._sync_tasks_table()

    def voice_hold_latch_allowed(self) -> bool:
        """Only latch hold-to-talk when `/voice` is on for the selected session."""
        skey = self._selected_session_key or ""
        sess = self._sessions_by_key.get(skey)
        return bool(skey) and self.controller.is_voice_enabled(
            skey, telemetry_voice_active=bool(sess is not None and sess.voice_active)
        )

    def _update_agent_action_buttons(self) -> None:
        skey = self._selected_session_key or ""
        sess = self._sessions_by_key.get(skey)
        live_pty = self.controller.pty_sessions.get(skey)
        pty_live = live_pty is not None and live_pty.alive
        voice_on = bool(
            skey
            and self.controller.is_voice_enabled(
                skey,
                telemetry_voice_active=bool(sess is not None and sess.voice_active),
            )
        )
        speaking = self.controller.tts.is_speaking
        queued = self.controller.tts.queue_size
        sig = (skey, pty_live, voice_on, speaking, queued)
        if sig == self._last_action_btn_sig:
            return
        self._last_action_btn_sig = sig
        try:
            btn_cli = self._main_query("#btn-agent-attach", Button)
            btn_cli.label = "CLI ●" if pty_live else "CLI"
            btn_cli.set_class(pty_live, "-pty-live")
        except NoMatches:
            pass
        try:
            btn_voice = self._main_query("#btn-agent-voice", Button)
            if speaking:
                btn_voice.label = f"🔊 Hablando (+{queued})" if queued > 0 else "🔊 Hablando…"
            elif voice_on:
                btn_voice.label = "🎤 Voz ON"
            else:
                btn_voice.label = "🎤 Voz"
            btn_voice.set_class(voice_on and not speaking, "-voice-on")
            btn_voice.set_class(speaking, "-voice-speaking")
        except NoMatches:
            pass

    def action_toggle_agent_view(self) -> None:
        cycle = {"terminal": "graph", "graph": "inspector", "inspector": "terminal", "log": "terminal"}
        self._agent_right_mode = cycle.get(self._agent_right_mode, "terminal")
        self._apply_agent_right_mode()

    def action_toggle_subagent_graph(self) -> None:
        self.action_switch_tab("tab-agents")
        self._agent_right_mode = "terminal" if self._agent_right_mode == "graph" else "graph"
        self._apply_agent_right_mode()

    def _attach_pty_now(
        self,
        sess: AgentSessionInfo,
        command_override: Optional[Sequence[str]] = None,
        banner: Optional[str] = None,
    ) -> Optional[PtySession]:
        self._agent_right_mode = "terminal"
        self._apply_agent_right_mode()
        try:
            term = self._main_query("#agent-terminal-pane", AgentTerminalWidget)
            cols = max(40, term.size.width - 2) if term.size.width > 20 else 90
            rows = max(10, term.size.height - 2) if term.size.height > 6 else 24
            prev_pty = term.pty_session
            pty_sess = self.controller.open_or_attach_pty(
                sess,
                cols=cols,
                rows=rows,
                command_override=command_override,
            )
            if banner and prev_pty is not pty_sess:
                pty_sess.screen.feed(banner)
            term.attach_pty(pty_sess)
            term.focus()
            self._update_agent_action_buttons()
            if prev_pty is not pty_sess:
                self.notify(f"CLI conectado en PTY: {sess.title} (Ctrl+G para salir de Modo Terminal)", timeout=2.5)
            return pty_sess
        except NoMatches:
            return None

    def action_attach_agent_pty(self) -> None:
        self.action_switch_tab("tab-agents")
        sess = self._sessions_by_key.get(self._selected_session_key or "")
        if sess is None:
            sess = self.controller.create_named_session("herdr-1")
            skey = f"{sess.tool}:{sess.session_id}"
            self._sessions_by_key[skey] = sess
            self._selected_session_key = skey
        else:
            skey = f"{sess.tool}:{sess.session_id}"

        existing = self.controller.pty_sessions.get(skey)
        if existing is not None and existing.alive:
            self._attach_pty_now(sess)
            return

        cli_info = self.controller.check_cli_availability(sess.tool)
        if not cli_info["installed"]:
            def _on_choice(choice: Optional[str]) -> None:
                if choice == "install":
                    banner = (
                        f"\x1b[1;38;2;217;177;95m◆ Instalando {cli_info['display_name']}...\x1b[0m\r\n"
                        f"\x1b[38;2;138;168;204m$ {cli_info['install_display']}\x1b[0m\r\n"
                        f"\x1b[38;2;148;163;184mNota: {cli_info['login_hint']}\x1b[0m\r\n\r\n"
                    )
                    self._attach_pty_now(sess, command_override=cli_info["install_argv"], banner=banner)
                elif choice == "shell":
                    banner = (
                        f"\x1b[1;38;2;217;177;95m◆ {cli_info['display_name']} no instalado (`{cli_info['binary']}`).\x1b[0m\r\n"
                        f"\x1b[38;2;138;168;204m  Instalar: {cli_info['install_display']}\x1b[0m\r\n"
                        f"\x1b[38;2;148;163;184m  {cli_info['login_hint']}\x1b[0m\r\n\r\n"
                    )
                    self._attach_pty_now(sess, command_override=cli_info["shell_argv"], banner=banner)

            self.push_screen(CliInstallScreen(cli_info), callback=_on_choice)
            return

        self._attach_pty_now(sess)

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
            if self._agent_right_mode == "graph" and focused_id not in ("agents-tasks-table", "agents-task-log"):
                sess = self._sessions_by_key.get(self._selected_session_key or "")
                out = format_subagent_graph(
                    sess,
                    list(self._sessions_by_key.values()),
                    list(self._all_tasks),
                )
                return f"Grafo de Subagentes · {sess.title if sess else '-'}", out, False
            if self._agent_right_mode == "log":
                task = self._tasks_by_key.get(self._selected_task_key or "")
                lines = list(task.tail_lines) if task else []
                out = Text()
                for ln in lines:
                    out.append_text(format_output_line(ln))
                    out.append("\n")
                return f"Log · {task.title if task else 'sin task'}", out or Text("(sin salida)"), False
            live_pty = self.controller.pty_sessions.get(self._selected_session_key or "")
            if live_pty is not None and (focused_id == "agent-terminal-pane" or self._agent_right_mode == "terminal"):
                live_pty.poll_output()
                sess = self._sessions_by_key.get(self._selected_session_key or "")
                out = format_session_detail_summary(sess)
                out.append("\n\n")
                out.append_text(live_pty.screen.render_rich(show_cursor=True))
                return f"Terminal PTY · {sess.title if sess else '-'}", out, False
            if (
                self._agent_right_mode == "inspector"
                and focused_id not in ("agents-tasks-table", "agents-task-log")
            ) or focused_id == "agents-activity-log" or (not self._selected_task_key and self._selected_session_key):
                sess = self._sessions_by_key.get(self._selected_session_key or "")
                out = format_session_detail_summary(sess)
                out.append("\n\n")
                for item in (sess.activities if sess else []):
                    out.append(f"{item.timestamp} [{item.kind}] {item.summary}\n")
                return f"Timeline · {sess.title if sess else '-'}", out, False
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
            kmode = self._knowledge_mode
            if kmode == "gotchas":
                g = self._gotchas_by_key.get(self._selected_gotcha_key or "")
                if g:
                    g_path = self.project_root / ".aos" / "knowledge" / "gotchas" / g["filename"]
                    body = g_path.read_text(encoding="utf-8", errors="replace") if g_path.is_file() else g["title"]
                    if body.startswith("---"):
                        parts = body.split("\n---", 1)
                        if len(parts) == 2:
                            body = parts[1].lstrip("\r\n")
                    header = f"> **{g['severity'].upper()}** · `{g['filename']}` · {g['date']}\n\n"
                    return f"Gotcha · {g['filename']}", header + body, True
            elif kmode == "rag":
                hit = self._rag_hits_by_key.get(self._selected_rag_key or "")
                if hit is not None:
                    out = Text()
                    out.append_text(kind_text(hit.kind))
                    out.append(f"  {hit.title}", style="bold #f8fafc")
                    if hit.section:
                        out.append(f" › {hit.section}", style="#8aa8cc")
                    out.append(f"\nRuta: {hit.path}  ·  Score: {hit.score:.4f}\n\n", style="#64748b")
                    out.append((hit.snippet or "(Sin extracto)").strip(), style="#e2e8f0")
                    return f"RAG · {hit.title}", out, False
            elif kmode == "health":
                out = Text()
                f = self._doctor_by_key.get(self._selected_doctor_key or "")
                if f is not None:
                    out.append("Hallazgo seleccionado\n", style="bold #d9b15f")
                    out.append("  ")
                    out.append_text(level_text(f.level))
                    out.append(f"  {f.area}\n  {f.message}\n\n", style="#e2e8f0")
                out.append("Todos los hallazgos (aos doctor)\n", style="bold #8aa8cc")
                for finding in self.snapshot.doctor_findings:
                    out.append("  ")
                    out.append_text(level_text(finding.level))
                    out.append(f"  {finding.area}  ", style="bold #f8fafc")
                    out.append(f"{finding.message}\n", style="#cbd5e1")
                out.append("\nAdaptación Nativa (adapt-native)\n", style="bold #8aa8cc")
                for tool, state in self.snapshot.native_tools.items():
                    out.append(f"  ● {tool:<14} {state}\n", style="#34d399" if "día" in state.lower() else "#fbbf24")
                if self.snapshot.missing_deps:
                    out.append("\nDependencias opcionales faltantes\n", style="bold #fbbf24")
                    for name, hint in self.snapshot.missing_deps:
                        out.append(f"  • {name:<10} {hint}\n", style="#94a3b8")
                return "Salud del Harness · Nativos · Dependencias", out, False
            elif kmode == "lessons":
                lesson = self._lessons_by_key.get(self._selected_lesson_key or "")
                if lesson:
                    return "Lección (LEDGER.md)", format_lesson_detail(lesson), False
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
        tab = self.query_one("#main-tabs", TabbedContent).active
        focused_id = self.focused.id if self.focused else ""
        if tab == "tab-agents" and focused_id not in ("agents-tasks-table", "agents-task-log"):
            skey = self._selected_session_key or ""
            sess = self._sessions_by_key.get(skey)
            live_pty = self.controller.pty_sessions.get(skey)
            if (
                sess is not None
                and self._agent_right_mode == "terminal"
                and focused_id != "agents-activity-log"
            ):
                if live_pty is None:
                    cli_info = self.controller.check_cli_availability(sess.tool)
                    if not cli_info["installed"]:
                        self.action_attach_agent_pty()
                        return
                    live_pty = self.controller.open_or_attach_pty(sess, cols=100, rows=28)
                    try:
                        self._main_query("#agent-terminal-pane", AgentTerminalWidget).attach_pty(live_pty)
                    except NoMatches:
                        pass
                live_pty.poll_output()
                self.push_screen(
                    ZoomScreen(
                        f"Terminal PTY · {sess.title}",
                        "",
                        is_markdown=False,
                        pty_session=live_pty,
                    ),
                    callback=self._on_zoom_closed,
                )
                return
        title, content, is_md = self._zoom_payload()
        self.push_screen(ZoomScreen(title, content, is_markdown=is_md))

    def _on_zoom_closed(self, result: Optional[str] = None) -> None:
        if result == "nav":
            # Textual restores focus to the main PTY on pop; override it after that.
            self.call_after_refresh(self.set_focus, None)
        try:
            term = self._main_query("#agent-terminal-pane", AgentTerminalWidget)
            term.refresh_viewport(force=True)
            self._last_session_sig = None
            self._render_selected_session()
        except NoMatches:
            pass

    def action_switch_tab(self, tab_id: str) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        if tabs.active != tab_id:
            # Clear focus inside the outgoing pane so Textual does not bounce back when hiding it.
            self.set_focus(None)
            tabs.active = tab_id
        if self.snapshot is not None:
            self._sync_tab(tab_id, self.snapshot)

    @on(TabbedContent.TabActivated, "#main-tabs")
    def handle_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        pane_id = event.pane.id if event.pane else ""
        if pane_id and self.snapshot is not None:
            self._sync_tab(pane_id, self.snapshot)

    def action_toggle_mute(self) -> None:
        muted = self.alerts.toggle_mute()
        if muted:
            self.controller.tts.stop()
        if self.snapshot is not None:
            self._update_header(self.snapshot)
        msg = "Alertas y sonido silenciados (m para activar)" if muted else "Alertas y sonido activados"
        self.notify(msg, timeout=2.0)

    def action_stop_voice(self) -> None:
        if isinstance(self.focused, Input):
            self.set_focus(None)
        if self.controller.tts.stop():
            self.notify("Locución de voz detenida", timeout=1.5)

    def _create_named_session(self, name: str, tool: str) -> None:
        sess = self.controller.create_named_session(
            name.strip() or f"herdr-{len(self.controller.named_sessions) + 1}",
            tool=tool,
        )
        skey = f"{sess.tool}:{sess.session_id}"
        self._sessions_by_key[skey] = sess
        self._selected_session_key = skey
        self._last_session_sig = None
        if self.snapshot is not None:
            self._update_agents_tab(self.snapshot)
        self._push_event(LiveEvent(time.strftime("%H:%M:%S"), "info", sess.tool, f"Nueva sesión creada: {sess.title}"))
        self.notify(f"Sesión creada: {sess.title}", timeout=2.0)

    def action_open_new_session_modal(self) -> None:
        self.action_switch_tab("tab-agents")
        selected = self._sessions_by_key.get(self._selected_session_key or "")
        default_tool = selected.tool if selected is not None else "claude-code"
        default_name = f"herdr-{len(self.controller.named_sessions) + 1}"

        def _on_done(result: Optional[Tuple[str, str]]) -> None:
            if result is not None:
                tool_choice, raw_name = result
                self._create_named_session(raw_name, tool_choice)

        self.push_screen(
            NewSessionScreen(default_tool=default_tool, default_name=default_name),
            callback=_on_done,
        )

    def action_new_agent_session(self) -> None:
        self.action_switch_tab("tab-agents")
        try:
            inp = self._main_query("#agent-prompt-input", Input)
            raw_name = inp.value.strip()
            inp.value = ""
        except NoMatches:
            raw_name = ""
        selected = self._sessions_by_key.get(self._selected_session_key or "")
        tool_choice = selected.tool if selected is not None else "claude-code"
        clean_name = raw_name
        low_raw = raw_name.lower()
        if low_raw.startswith(("agy:", "ag:")):
            tool_choice = "antigravity"
            clean_name = raw_name.split(":", 1)[1].strip()
        elif low_raw.startswith(("cc:", "claude:")):
            tool_choice = "claude-code"
            clean_name = raw_name.split(":", 1)[1].strip()
        self._create_named_session(clean_name, tool_choice)

    def _send_pty_voice_toggle(self, pty_sess: PtySession, tool: str, active: bool) -> None:
        """Forward native voice toggle to a live `claude-code` or `antigravity` PTY."""
        if not pty_sess.alive:
            return

        def _send_cr() -> None:
            if pty_sess.alive:
                pty_sess.write("\r")

        if active:
            pty_sess.write("/voice")
            self.set_timer(0.15, _send_cr)
        elif tool == "antigravity":
            # In Antigravity CLI, F7 hangs up the live voice session cleanly
            pty_sess.write("\x1b[18~")
        else:
            # In Claude Code CLI, `/voice` toggles voice mode off
            pty_sess.write("/voice")
            self.set_timer(0.15, _send_cr)

    def action_toggle_voice_mode(self) -> None:
        skey = self._selected_session_key
        if not skey:
            self.notify("Selecciona primero una sesión en Agentes.", severity="warning", timeout=2.0)
            return
        sess = self._sessions_by_key.get(skey)
        was_on = self.controller.is_voice_enabled(
            skey,
            telemetry_voice_active=bool(sess is not None and sess.voice_active),
        )
        active = self.controller.toggle_voice(skey, currently_active=was_on)
        pty_sess = self.controller.pty_sessions.get(skey)
        if pty_sess is not None and pty_sess.alive:
            tool = sess.tool if sess is not None else skey.split(":", 1)[0]
            self._send_pty_voice_toggle(pty_sess, tool, active)
        if active and sess and sess.last_assistant_text and not self.alerts.muted:
            self.controller.tts.speak(sess.last_assistant_text)
        self._last_session_sig = None
        self._last_action_btn_sig = None
        try:
            self._render_selected_session()
            self._update_agent_action_buttons()
        except NoMatches:
            pass
        if active:
            if pty_sess is not None and pty_sess.alive:
                label = "activado (/voice en CLI + cola TTS)"
            else:
                label = "activado (cola TTS · conecta CLI para dictado /voice)"
        else:
            label = "desactivado"
        self.notify(f"Modo voz {label}", timeout=2.0)

    def action_stop_agent_session(self) -> None:
        stopped_proc = self.controller.stop_active_process(self._selected_session_key)
        stopped_tts = self.controller.tts.stop()
        try:
            term = self._main_query("#agent-terminal-pane", AgentTerminalWidget)
            if term.pty_session and not term.pty_session.alive:
                term.attach_pty(None)
            if self.focused is term:
                try:
                    self._main_query("#agents-sessions-table", DataTable).focus()
                except NoMatches:
                    self.set_focus(None)
        except NoMatches:
            pass
        self._last_session_sig = None
        try:
            self._render_selected_session()
            self._update_agent_action_buttons()
        except NoMatches:
            pass
        if stopped_proc or stopped_tts:
            self.notify("Proceso / PTY / voz de sesión detenido.", timeout=2.0)
        else:
            self.notify("No hay proceso gestionado activo para detener.", timeout=1.5)

    def action_refresh_now(self) -> None:
        self._refresh_worker(force_slow=True, force_deps=True)
        self.notify("Snapshot actualizado", timeout=1.5)

    def action_focus_rag(self) -> None:
        self.action_switch_tab("tab-knowledge")
        self.query_one("#rag-input", Input).focus()

    def action_run_verify(self) -> None:
        self._start_aos_command("verify", ["verify"])

    def action_run_scan(self) -> None:
        self._start_aos_command("scan", ["scan", "--dry-run"])

    def action_run_update(self) -> None:
        self._start_aos_command("update", ["update"])

    def action_run_sync(self) -> None:
        self._start_aos_command("sync", ["sync"])

    def action_run_refresh_cmd(self) -> None:
        self._start_aos_command("refresh", ["refresh"])

    @on(Button.Pressed)
    def handle_runner_buttons(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-view-terminal":
            self._set_agent_right_mode("terminal")
            return
        if bid == "btn-view-inspector":
            self._set_agent_right_mode("inspector")
            return
        if bid == "btn-view-graph":
            self._set_agent_right_mode("graph")
            return
        if bid == "btn-view-log":
            self._set_agent_right_mode("log")
            return
        if bid == "btn-tasks-filter-session":
            self._set_tasks_filter("session")
            return
        if bid == "btn-tasks-filter-all":
            self._set_tasks_filter("all")
            return
        if bid == "btn-know-rag":
            self._set_knowledge_mode("rag")
            return
        if bid == "btn-know-gotchas":
            self._set_knowledge_mode("gotchas")
            return
        if bid == "btn-know-health":
            self._set_knowledge_mode("health")
            return
        if bid == "btn-know-lessons":
            self._set_knowledge_mode("lessons")
            return
        if bid == "btn-agent-attach":
            self.action_attach_agent_pty()
            return
        if bid == "btn-agent-zoom":
            self.action_toggle_zoom()
            return
        if bid == "btn-agent-new":
            self.action_open_new_session_modal()
            return
        if bid == "btn-agent-voice":
            self.action_toggle_voice_mode()
            return
        if bid == "btn-agent-stop":
            self.action_stop_agent_session()
            return
        mapping = {
            "btn-verify": ("verify", ["verify"]),
            "btn-scan": ("scan", ["scan", "--dry-run"]),
            "btn-update": ("update", ["update"]),
            "btn-doctor": ("doctor", ["doctor"]),
        }
        if bid in mapping:
            label, args = mapping[bid]
            self._start_aos_command(label, args)

    @on(Input.Submitted, "#rag-input")
    def handle_rag_submit(self, event: Input.Submitted) -> None:
        self._set_knowledge_mode("rag")
        self._rag_worker(event.value.strip())

    @on(Input.Submitted, "#agent-prompt-input")
    def handle_agent_prompt_submit(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        if not prompt:
            return
        event.input.value = ""
        if prompt.lower() == "/voice":
            self.action_toggle_voice_mode()
            return
        self.controller.tts.stop()
        sess = self._sessions_by_key.get(self._selected_session_key or "")
        if sess is None:
            sess = self.controller.create_named_session("herdr-main")
            skey = f"{sess.tool}:{sess.session_id}"
            self._sessions_by_key[skey] = sess
            self._selected_session_key = skey
        else:
            skey = f"{sess.tool}:{sess.session_id}"
        pty_sess = self.controller.pty_sessions.get(skey)
        if pty_sess is not None and pty_sess.alive:
            pty_sess.write(prompt + "\r")
            try:
                self._main_query("#agent-terminal-pane", AgentTerminalWidget).refresh_viewport()
            except NoMatches:
                pass
            return
        self._session_prompt_worker(sess, prompt)

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
                self._update_agent_action_buttons()
                self._sync_tasks_table()
            except NoMatches:
                pass

    @on(DataTable.RowSelected, "#agents-sessions-table")
    def handle_session_selected(self, event: DataTable.RowSelected) -> None:
        self._on_session_row(event.row_key)
        self.action_attach_agent_pty()

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
        if self._selected_task_key in self._tasks_by_key:
            self._set_agent_right_mode("log")

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

    def _on_knowledge_row(self, kind: str, row_key: Any) -> None:
        if not self.is_mounted or not self.screen_stack:
            return
        key = str(row_key.value)
        if kind == "rag" and key in self._rag_hits_by_key:
            self._selected_rag_key = key
        elif kind == "gotchas" and key in self._gotchas_by_key:
            self._selected_gotcha_key = key
        elif kind == "health" and key in self._doctor_by_key:
            self._selected_doctor_key = key
        elif kind == "lessons" and key in self._lessons_by_key:
            self._selected_lesson_key = key
        else:
            return
        self._render_knowledge_detail()

    @on(DataTable.RowSelected, "#rag-results-table")
    def handle_rag_row_selected(self, event: DataTable.RowSelected) -> None:
        self._on_knowledge_row("rag", event.row_key)

    @on(DataTable.RowHighlighted, "#rag-results-table")
    def handle_rag_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._on_knowledge_row("rag", event.row_key)

    @on(DataTable.RowSelected, "#gotchas-table")
    def handle_gotcha_row_selected(self, event: DataTable.RowSelected) -> None:
        self._on_knowledge_row("gotchas", event.row_key)

    @on(DataTable.RowHighlighted, "#gotchas-table")
    def handle_gotcha_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._on_knowledge_row("gotchas", event.row_key)

    @on(DataTable.RowSelected, "#doctor-table")
    def handle_doctor_row_selected(self, event: DataTable.RowSelected) -> None:
        self._on_knowledge_row("health", event.row_key)

    @on(DataTable.RowHighlighted, "#doctor-table")
    def handle_doctor_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._on_knowledge_row("health", event.row_key)

    @on(DataTable.RowSelected, "#lessons-table")
    def handle_lesson_row_selected(self, event: DataTable.RowSelected) -> None:
        self._on_knowledge_row("lessons", event.row_key)

    @on(DataTable.RowHighlighted, "#lessons-table")
    def handle_lesson_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._on_knowledge_row("lessons", event.row_key)

    @work(thread=True, exclusive=True, group="telemetry")
    def _refresh_worker(self, force_slow: bool = False, force_deps: bool = False) -> None:
        self._refreshing = True
        try:
            now = time.time()
            try:
                active_tab = self._main_query("#main-tabs", TabbedContent).active or "tab-overview"
            except Exception:
                active_tab = "tab-overview"
            run_slow = force_slow or (
                self.snapshot is not None
                and (now - self._last_slow_check_ts) >= _SLOW_CHECK_INTERVAL_SECONDS
            )
            git_focused = active_tab in ("tab-overview", "tab-git")
            run_git = (
                force_slow
                or self.snapshot is None
                or git_focused
                or (now - self._last_git_check_ts) >= _IDLE_GIT_INTERVAL_SECONDS
            )
            snap = collect_telemetry(
                self.project_root,
                claude_home=self.claude_home,
                antigravity_home=self.antigravity_home,
                prev_snapshot=self.snapshot,
                include_slow=run_slow,
                include_git=run_git,
                force_deps=force_deps,
            )
            if run_slow:
                self._last_slow_check_ts = now
            if run_git:
                self._last_git_check_ts = now
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

        # Preserve live PTY status on snapshot sessions so snapshot & PTY ticks stay consistent
        for sess in snap.sessions:
            skey = f"{sess.tool}:{sess.session_id}"
            pty_s = self.controller.pty_sessions.get(skey)
            if pty_s is not None and pty_s.alive:
                st, reason = detect_terminal_agent_state(pty_s.screen)
                if st == "pending":
                    sess.status = "pending"
                    sess.pending_reason = reason or "Esperando acción en terminal"
                elif st == "running":
                    sess.status = "running"
                    sess.pending_reason = ""
                else:
                    sess.status = "active"
                    sess.pending_reason = ""

        # CA-4: Fire multi-channel pending alerts (TUI banner/toast + sound + OS toast)
        newly_pending = self.alerts.process_sessions(snap.sessions)
        for psess in newly_pending:
            reason = psess.pending_reason or "Esperando aprobación o respuesta"
            self.notify(f"⚠ PENDING ({psess.title}): {reason}", severity="warning", timeout=5.0)

        # CA-6: Speak assistant response when `/voice` is active on a session
        if not self.alerts.muted:
            self.controller.sync_voice_sessions(snap.sessions)

        all_tabs = {
            "tab-overview",
            "tab-plans",
            "tab-agents",
            "tab-git",
            "tab-knowledge",
            "tab-tokens",
        }
        self._dirty_tabs.update(all_tabs)

        try:
            self._update_header(snap)
            active_tab = self._main_query("#main-tabs", TabbedContent).active or "tab-overview"
            self._sync_tab(active_tab, snap)
        except NoMatches:
            return
        if not self._rag_initialized:
            self._rag_initialized = True
            self._rag_worker("")

    def _sync_tab(self, tab_id: str, snap: TelemetrySnapshot) -> None:
        """Lazily update only the requested tab (`CA-1`)."""
        if tab_id not in self._dirty_tabs and tab_id != "tab-agents":
            return
        self._dirty_tabs.discard(tab_id)
        try:
            if tab_id == "tab-overview":
                self._update_overview(snap)
            elif tab_id == "tab-plans":
                self._update_plans_tab(snap)
            elif tab_id == "tab-agents":
                self._update_agents_tab(snap)
            elif tab_id == "tab-git":
                self._update_git_tab(snap)
            elif tab_id == "tab-knowledge":
                self._update_knowledge_tab(snap)
            elif tab_id == "tab-tokens":
                self._update_tokens_tab(snap)
        except NoMatches:
            pass

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
        if self.alerts.muted:
            info.append("  [MUTE]", style="bold #94a3b8")
        pending_list = [s for s in snap.sessions if s.status == "pending"]
        if pending_list:
            info.append(f"  ⚠ {len(pending_list)} PENDING", style="bold #0b1120 on #fbbf24")
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
        combined_sessions: List[AgentSessionInfo] = []
        seen_keys: Set[str] = set()
        for sess in snap.sessions:
            skey = f"{sess.tool}:{sess.session_id}"
            if skey in self.controller.named_sessions:
                self.controller.named_sessions[skey] = sess
            if skey not in seen_keys:
                combined_sessions.append(sess)
                seen_keys.add(skey)
        for skey, nsess in self.controller.named_sessions.items():
            if skey not in seen_keys:
                combined_sessions.insert(0, nsess)
                seen_keys.add(skey)

        for sess in combined_sessions:
            skey = f"{sess.tool}:{sess.session_id}"
            self._sessions_by_key[skey] = sess
            title_txt = " ".join(sess.title.split())[:28]
            if self.controller.is_voice_enabled(skey, telemetry_voice_active=sess.voice_active):
                title_txt = f"🎤 {title_txt}"
            sess_rows.append((
                skey,
                (
                    agent_badge(sess.tool),
                    Text(title_txt, style="#e2e8f0"),
                    status_text(sess.status),
                    Text(compact_age(sess.updated_at), style="#94a3b8"),
                ),
            ))
        if not sess_rows:
            sess_rows.append((None, ("-", "Sin sesiones locales para este repo", "-", "-")))

        if self._selected_session_key not in self._sessions_by_key:
            self._selected_session_key = next(iter(self._sessions_by_key), None)
        self._main_query("#agents-sessions-box").border_title = f"Sesiones ({len(combined_sessions)})"
        self._sync_table("#agents-sessions-table", sess_rows, preserve_key=self._selected_session_key)
        self._render_selected_session()
        self._update_agent_action_buttons()

        self._all_tasks = list(self._runner_jobs) + list(snap.tasks)
        self._sync_tasks_table()

    def _task_belongs_to_session(self, task: AgentTaskInfo, sess: Optional[AgentSessionInfo]) -> bool:
        if sess is None or not task.session_id:
            return False
        return (
            task.session_id == sess.session_id
            or sess.session_id.startswith(task.session_id)
            or task.session_id.startswith(sess.session_id)
        )

    def _sync_tasks_table(self) -> None:
        self._tasks_by_key.clear()
        sess = self._sessions_by_key.get(self._selected_session_key or "")
        session_tasks = [t for t in self._all_tasks if self._task_belongs_to_session(t, sess)]
        all_count = len(self._all_tasks)
        sess_count = len(session_tasks)

        try:
            self._main_query("#btn-tasks-filter-session", Button).label = f"Sesión ({sess_count})"
            self._main_query("#btn-tasks-filter-all", Button).label = f"Todas ({all_count})"
        except NoMatches:
            pass

        visible_tasks = session_tasks if self._tasks_filter_mode == "session" else self._all_tasks
        task_rows: List[Tuple[Optional[str], Sequence[Any]]] = []
        for idx, task in enumerate(visible_tasks):
            tkey = f"{task.agent}:{task.session_id}:{task.id}"
            if tkey in self._tasks_by_key:
                tkey = f"{tkey}:{idx}"
            self._tasks_by_key[tkey] = task
            label = Text(re.sub(r"\.log$", "", task.title or task.id)[:28], style="#e2e8f0")
            if self._tasks_filter_mode == "all" and task.session_id and task.agent != "tui-runner":
                label.append(f"  {task.session_id[:6]}", style="#475569")
            task_rows.append((
                tkey,
                (
                    agent_badge(task.agent),
                    label,
                    status_text(task.status),
                    Text(format_task_time_compact(task.started_at, task.updated_at), style="#94a3b8"),
                ),
            ))
        if not task_rows:
            if self._tasks_filter_mode == "session" and all_count > 0:
                empty_msg = f"Sin tasks en esta sesión ({all_count} en Todas)"
            else:
                empty_msg = "Sin tasks en background"
            task_rows.append((None, ("-", empty_msg, "-", "-")))

        if self._selected_task_key not in self._tasks_by_key:
            self._selected_task_key = next(iter(self._tasks_by_key), None)
        self._sync_table("#agents-tasks-table", task_rows, preserve_key=self._selected_task_key)
        self._render_selected_task()

    def _render_selected_session(self) -> None:
        skey = self._selected_session_key or ""
        sess = self._sessions_by_key.get(skey)
        voice_on = bool(
            skey
            and self.controller.is_voice_enabled(
                skey,
                telemetry_voice_active=bool(sess is not None and sess.voice_active),
            )
        )
        live_pty = self.controller.pty_sessions.get(skey)
        mode = self._agent_right_mode
        is_compact = mode in ("terminal", "graph")
        sig = (
            sess.tool,
            sess.session_id,
            sess.status,
            sess.pending_reason,
            voice_on,
            mode,
            live_pty is not None,
            live_pty.alive if live_pty is not None else False,
            len(sess.subagents),
            len(sess.workflows),
            len(sess.touched_files),
            len(sess.activities),
            sess.activities[-1].summary if sess.activities else "",
            len(self._all_tasks) if mode == "graph" else 0,
        ) if sess else None
        if sig == self._last_session_sig:
            return
        self._last_session_sig = sig

        self._main_query("#agents-session-summary", Static).update(
            format_session_detail_summary(sess, voice_enabled=voice_on, compact=is_compact)
        )
        try:
            term = self._main_query("#agent-terminal-pane", AgentTerminalWidget)
            if live_pty is not None:
                term.attach_pty(live_pty)
            else:
                term.pty_session = None
                preview = Text()
                if sess:
                    cli_info = self.controller.check_cli_availability(sess.tool)
                    if not cli_info["installed"]:
                        preview.append(f"\n  ▲ {cli_info['display_name']} no instalado (`{cli_info['binary']}` no está en PATH)\n", style="bold #fbbf24")
                        preview.append(f"  Instalar: {cli_info['install_display']}\n", style="bold #8aa8cc")
                        preview.append(f"  Login:    {cli_info['login_hint']}\n\n", style="#cbd5e1")
                        preview.append("  • Pulsa ", style="#64748b")
                        preview.append("Enter", style="bold #d9b15f")
                        preview.append(" o clic en ", style="#64748b")
                        preview.append("CLI", style="bold #d9b15f")
                        preview.append(" para instalarlo ahora desde aquí o abrir un shell.\n", style="#64748b")
                    else:
                        cli_hint = (
                            f"agy --conversation {sess.session_id[:8]}…"
                            if sess.tool == "antigravity"
                            else f"claude --resume {sess.session_id[:8]}…"
                        )
                        preview.append("\n  Terminal desconectado\n", style="bold #94a3b8")
                        preview.append(f"  Comando: {cli_hint}\n\n", style="#8aa8cc")
                        preview.append("  • Pulsa ", style="#64748b")
                        preview.append("Enter", style="bold #d9b15f")
                        preview.append(" sobre la sesión o clic en ", style="#64748b")
                        preview.append("CLI", style="bold #d9b15f")
                        preview.append(" para abrir el PTY interactivo.\n", style="#64748b")
                        preview.append("  • Usa las pestañas ", style="#64748b")
                        preview.append("Timeline · Grafo · Log", style="#cbd5e1")
                        preview.append(" arriba para inspeccionar sin conectar.\n", style="#64748b")
                else:
                    preview.append("\n  Selecciona una sesión a la izquierda o pulsa '+ Nueva'.\n", style="#64748b")
                term.update(preview)
        except NoMatches:
            pass
        log = self._main_query("#agents-activity-log", RichLog)
        log.clear()
        if not sess:
            return
        if mode == "graph":
            log.write(
                format_subagent_graph(
                    sess,
                    list(self._sessions_by_key.values()),
                    list(self._all_tasks),
                )
            )
            return
        if not sess.activities:
            log.write(Text("Sin eventos recientes. Escribe abajo para enviar un prompt a esta sesión.", style="#64748b"))
            return
        for item in sess.activities:
            log.write(format_activity_row(item))

    def _render_selected_task(self) -> None:
        task = self._tasks_by_key.get(self._selected_task_key or "")
        box = self._main_query("#agents-log-box")
        log = self._main_query("#agents-task-log", RichLog)
        if not task:
            box.border_title = "Log de Task"
            if self._last_task_tail_sig is not None or log.lines == []:
                log.clear()
                log.write(Text("Selecciona una task a la izquierda para inspeccionar su log en vivo.", style="#64748b"))
                self._last_task_tail_sig = None
            return
        lines = list(task.tail_lines)
        sig = (
            task.agent,
            task.session_id,
            task.id,
            task.status,
            task.started_at,
            task.updated_at,
            len(lines),
            lines[-1] if lines else "",
        )
        if sig == self._last_task_tail_sig:
            return
        self._last_task_tail_sig = sig
        box.border_title = format_task_log_header(task)
        log.clear()
        for line in lines:
            log.write(format_output_line(line))

    @work(thread=True, exclusive=True, group="agent-prompt")
    def _session_prompt_worker(self, sess: AgentSessionInfo, prompt: str) -> None:
        skey = f"{sess.tool}:{sess.session_id}"
        is_resume = sess.meta != "nueva (TUI)"
        cmd = self.controller.build_prompt_command(
            tool=sess.tool,
            prompt=prompt,
            session_id=sess.session_id,
            session_name=sess.title if not is_resume else None,
            resume=is_resume,
        )
        now_hms = time.strftime("%H:%M:%S")
        sess.status = "running"
        sess.pending_reason = ""
        sess.updated_at = time.time()
        sess.activities.append(AgentActivityItem(timestamp=now_hms, agent="user", kind="prompt", summary=f"Prompt: {prompt}"))

        def _on_start() -> None:
            self._last_session_sig = None
            self._push_event(LiveEvent(now_hms, "info", sess.tool, f"Prompt -> {sess.title}: {prompt[:48]}"))
            try:
                self._render_selected_session()
            except NoMatches:
                pass

        self.call_from_thread(_on_start)

        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        last_assistant: Optional[str] = None
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
                self.controller.active_proc = proc
                self.controller.active_session_key = skey
                if proc.stdout is not None:
                    for raw_line in proc.stdout:
                        disp_lines, asst_txt = self.controller.parse_stream_json_line(raw_line)
                        if asst_txt:
                            last_assistant = asst_txt
                            sess.last_assistant_text = asst_txt
                        for dln in disp_lines:
                            sess.activities.append(
                                AgentActivityItem(
                                    timestamp=time.strftime("%H:%M:%S"),
                                    agent=sess.tool,
                                    kind="stream",
                                    summary=f"Stream: {dln}",
                                )
                            )
                        if disp_lines:
                            self.call_from_thread(self._refresh_session_stream_view)
                proc.wait()
        except OSError as exc:
            sess.activities.append(
                AgentActivityItem(
                    timestamp=time.strftime("%H:%M:%S"),
                    agent=sess.tool,
                    kind="error",
                    summary=f"Error: {exc}",
                )
            )
        finally:
            self.controller.active_proc = None
            self.controller.active_session_key = None
            sess.status = "active"
            sess.meta = "activa (TUI)"
            sess.updated_at = time.time()
            if last_assistant and self.controller.is_voice_enabled(skey, telemetry_voice_active=sess.voice_active) and not self.alerts.muted:
                self.controller.tts.speak(last_assistant)
            try:
                self.call_from_thread(self._refresh_session_stream_view)
            except RuntimeError:
                pass

    def _refresh_session_stream_view(self) -> None:
        if not self.is_mounted or not self.screen_stack:
            return
        self._last_session_sig = None
        try:
            self._render_selected_session()
        except NoMatches:
            pass

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
            commits_log.write(format_git_commit_line(c))

        if self._selected_git_path:
            self._diff_worker(self._selected_git_path)
        else:
            diff_box = self._main_query("#git-diff-box")
            diff_box.border_title = "Diff del Archivo Seleccionado"
            diff_box.border_subtitle = ""
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
            diff_box = self._main_query("#git-diff-box")
            diff_box.border_title = f"Diff · {rel_path}"
            added, removed, hunks = diff_stats(diff_text)
            if hunks > 0:
                h_lbl = "hunk" if hunks == 1 else "hunks"
                diff_box.border_subtitle = f"[bold #34d399]+{added}[/]  [bold #f87171]−{removed}[/]  [dim]{hunks} {h_lbl} · z Zoom[/]"
            else:
                diff_box.border_subtitle = "[dim]z Zoom[/]"
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

    def _set_knowledge_mode(self, mode: str) -> None:
        if mode not in ("rag", "gotchas", "health", "lessons"):
            return
        self._knowledge_mode = mode
        self._apply_knowledge_mode()

    def _apply_knowledge_mode(self) -> None:
        mode = self._knowledge_mode
        boxes = {
            "#rag-results-box": "rag",
            "#gotchas-box": "gotchas",
            "#doctor-box": "health",
            "#lessons-box": "lessons",
        }
        pills = {
            "#btn-know-rag": "rag",
            "#btn-know-gotchas": "gotchas",
            "#btn-know-health": "health",
            "#btn-know-lessons": "lessons",
        }
        for sel, target in boxes.items():
            try:
                self._main_query(sel).display = (mode == target)
            except NoMatches:
                pass
        for sel, target in pills.items():
            try:
                self._main_query(sel, Button).set_class(mode == target, "-active")
            except NoMatches:
                pass
        self._render_knowledge_detail()

    def _update_knowledge_tab(self, snap: TelemetrySnapshot) -> None:
        self._gotchas_by_key.clear()
        gotcha_rows: List[Tuple[Optional[str], Sequence[Any]]] = []
        for idx, g in enumerate(snap.gotchas):
            key = f"g:{g['filename']}:{idx}"
            self._gotchas_by_key[key] = g
            title_short = g["title"] if len(g["title"]) <= 34 else g["title"][:33] + "…"
            gotcha_rows.append((key, (severity_text(g["severity"]), title_short, g["date"])))
        if not gotcha_rows:
            gotcha_rows.append((None, ("-", "Sin gotchas registrados", "-")))
        if self._selected_gotcha_key not in self._gotchas_by_key:
            self._selected_gotcha_key = next(iter(self._gotchas_by_key), None)
        self._sync_table("#gotchas-table", gotcha_rows, preserve_key=self._selected_gotcha_key)

        self._doctor_by_key.clear()
        doctor_rows: List[Tuple[Optional[str], Sequence[Any]]] = []
        for idx, f in enumerate(snap.doctor_findings):
            key = f"d:{idx}"
            self._doctor_by_key[key] = f
            msg_short = f.message if len(f.message) <= 34 else f.message[:33] + "…"
            doctor_rows.append((key, (level_text(f.level), f.area[:18], msg_short)))
        if not doctor_rows:
            doctor_rows.append((None, (Text("OK", style="bold #34d399"), "harness", "0 hallazgos")))
        if self._selected_doctor_key not in self._doctor_by_key:
            self._selected_doctor_key = next(iter(self._doctor_by_key), None)
        self._sync_table("#doctor-table", doctor_rows, preserve_key=self._selected_doctor_key)

        self._lessons_by_key.clear()
        lesson_rows: List[Tuple[Optional[str], Sequence[Any]]] = []
        for idx, lesson in enumerate(snap.lessons):
            key = f"l:{idx}"
            self._lessons_by_key[key] = lesson
            date_s, artifact_s, effect_s, _ev = parse_lesson_entry(lesson)
            clean_summary = f"{artifact_s}: {effect_s}" if artifact_s else effect_s
            clean_summary = clean_summary.replace("`", "")
            summary_short = clean_summary if len(clean_summary) <= 38 else clean_summary[:37] + "…"
            lesson_rows.append((key, (Text(date_s, style="#8aa8cc"), summary_short)))
        if not lesson_rows:
            lesson_rows.append((None, ("-", "Sin lecciones en LEDGER.md")))
        if self._selected_lesson_key not in self._lessons_by_key:
            self._selected_lesson_key = next(iter(self._lessons_by_key), None)
        self._sync_table("#lessons-table", lesson_rows, preserve_key=self._selected_lesson_key)

        err_n = sum(1 for f in snap.doctor_findings if f.level == "error")
        warn_n = sum(1 for f in snap.doctor_findings if f.level == "warn")
        health_tag = f"{err_n} err" if err_n else (f"{warn_n} warn" if warn_n else f"{len(snap.doctor_findings)} info")
        try:
            self._main_query("#btn-know-gotchas", Button).label = f"Gotchas ({len(snap.gotchas)})"
            self._main_query("#btn-know-health", Button).label = f"Salud & Nativos ({health_tag})"
            self._main_query("#btn-know-lessons", Button).label = f"Lecciones ({len(snap.lessons)})"
        except NoMatches:
            pass
        self._render_knowledge_detail()

    def _render_knowledge_detail(self) -> None:
        if not self.is_mounted or not self.screen_stack:
            return
        try:
            box = self._main_query("#knowledge-detail-box")
            log = self._main_query("#knowledge-detail-log", RichLog)
        except NoMatches:
            return
        log.clear()
        mode = self._knowledge_mode
        snap = self.snapshot

        if mode == "rag":
            hit = self._rag_hits_by_key.get(self._selected_rag_key or "")
            if hit is not None:
                box.border_title = f"Fragmento RAG · {hit.kind.upper()} ({hit.score:.2f})"
                box.border_subtitle = hit.path
                hdr = Text()
                hdr.append_text(kind_text(hit.kind))
                hdr.append(f"  {hit.title}", style="bold #f8fafc")
                if hit.section:
                    hdr.append(f" › {hit.section}", style="#8aa8cc")
                hdr.append(f"\nRuta:  {hit.path}", style="#64748b")
                hdr.append(f"   ·   Score: {hit.score:.4f}\n", style="#94a3b8")
                log.write(hdr)
                snippet = (hit.snippet or "").strip()
                if snippet:
                    log.write(Text(snippet, style="#e2e8f0"))
                else:
                    log.write(Text("(Sin extracto disponible)", style="#64748b"))
                return

            box.border_title = "Memoria del Proyecto (aos context)"
            box.border_subtitle = "↑/↓ navegar · / buscar · z Zoom"
            info = Text()
            if self._rag_last is not None:
                r = self._rag_last
                info.append("Motor de recuperación:  ", style="bold #94a3b8")
                info.append(f"{r.mode}", style="bold #8aa8cc")
                info.append(f"  ({r.indexed_files} archivos indexados en .aos/)\n", style="#cbd5e1")
                if r.note:
                    info.append(f"\nEstado: {r.note}\n", style="#fbbf24")
            info.append("\nQué muestra esta vista:\n", style="bold #d9b15f")
            info.append(
                "Simula exactamente el contexto que `aos context` inyecta a un agente "
                "al iniciar una tarea (gotchas, ADRs, specs PRD/TRD, lecciones y contratos).\n\n",
                style="#cbd5e1",
            )
            info.append("Cómo probarla:\n", style="bold #8aa8cc")
            info.append("  • Pulsa ", style="#94a3b8")
            info.append("/", style="bold #d9b15f")
            info.append(" y escribe un tema técnico (ej. `conpty`, `tokens`, `auth`, `tui`).\n", style="#cbd5e1")
            info.append("  • Selecciona cualquier fila a la izquierda para leer el fragmento completo.\n", style="#cbd5e1")
            log.write(info)
            return

        if mode == "gotchas":
            g = self._gotchas_by_key.get(self._selected_gotcha_key or "")
            if not g:
                box.border_title = "Detalle de Gotcha"
                box.border_subtitle = ""
                log.write(Text("Sin gotchas registrados en .aos/knowledge/gotchas/.", style="#64748b"))
                return
            box.border_title = f"Gotcha · {g['filename']}"
            box.border_subtitle = f"{g['severity'].upper()} · {g['date']}"
            hdr = Text()
            hdr.append_text(severity_text(g["severity"]))
            hdr.append(f"  {g['title']}\n", style="bold #f8fafc")
            hdr.append(f"Archivo: .aos/knowledge/gotchas/{g['filename']}  ·  Fecha: {g['date']}\n", style="#64748b")
            log.write(hdr)
            g_path = self.project_root / ".aos" / "knowledge" / "gotchas" / g["filename"]
            if g_path.is_file():
                body = g_path.read_text(encoding="utf-8", errors="replace")
                if body.startswith("---"):
                    parts = body.split("\n---", 1)
                    if len(parts) == 2:
                        body = parts[1].lstrip("\r\n")
                log.write(RichMarkdown(body), expand=True)
            return

        if mode == "health":
            box.border_title = "Salud del Harness · Nativos · Dependencias"
            box.border_subtitle = "aos doctor + adapt-native"
            f = self._doctor_by_key.get(self._selected_doctor_key or "")
            if f is not None:
                ft = Text()
                ft.append("Hallazgo seleccionado\n", style="bold #d9b15f")
                ft.append("  ")
                ft.append_text(level_text(f.level))
                ft.append(f"  {f.area}\n", style="bold #f8fafc")
                ft.append(f"  {f.message}\n\n", style="#e2e8f0")
                log.write(ft)
            if snap is not None:
                nt = Text()
                nt.append("Adaptación Nativa (adapt-native)\n", style="bold #8aa8cc")
                if snap.native_tools:
                    for tool, state in snap.native_tools.items():
                        color = "#34d399" if "día" in state.lower() else "#fbbf24"
                        nt.append(f"  ● {tool:<14} ", style="bold #f8fafc")
                        nt.append(f"{state}\n", style=color)
                else:
                    nt.append("  (sin herramientas nativas configuradas)\n", style="#64748b")

                # Show missing deps only if not already fully covered in doctor findings, or as actionable install block
                if snap.missing_deps:
                    nt.append("\nInstalación de dependencias opcionales\n", style="bold #fbbf24")
                    for name, hint in snap.missing_deps:
                        nt.append(f"  • {name:<10} ", style="bold #e2e8f0")
                        nt.append(f"{hint}\n", style="#94a3b8")
                log.write(nt)
            return

        # lessons mode
        lesson = self._lessons_by_key.get(self._selected_lesson_key or "")
        box.border_title = "Lección Registrada (LEDGER.md)"
        box.border_subtitle = ".aos/knowledge/lessons/LEDGER.md · z Zoom"
        if not lesson:
            log.write(Text("Sin lecciones registradas en .aos/knowledge/lessons/LEDGER.md.", style="#64748b"))
            return
        log.write(format_lesson_detail(lesson))

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
            if s.cost_usd > 0:
                cost_s = f"~${s.cost_usd:.2f}" if s.cost_estimated else f"${s.cost_usd:.2f}"
            else:
                cost_s = "-"
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
            idx_count = getattr(self._rag_last, "indexed_files", 0) if self._rag_last is not None else 0
            badge_txt = f"RAG: {mode} · {idx_count} arch." if idx_count else f"RAG: {mode}"
            self._main_query("#rag-mode-badge", Static).update(badge_txt)
            self._main_query("#btn-know-rag", Button).label = f"Memoria RAG ({len(hits)})"
        except NoMatches:
            return
        self._rag_hits_by_key.clear()
        rows: List[Tuple[Optional[str], Sequence[Any]]] = []
        for idx, hit in enumerate(hits):
            key = f"rag:{idx}"
            self._rag_hits_by_key[key] = hit
            label = f"{hit.title} › {hit.section}" if hit.section else hit.title
            label_short = label if len(label) <= 36 else label[:35] + "…"
            rows.append((
                key,
                (
                    kind_text(hit.kind),
                    f"{hit.score:.2f}",
                    label_short,
                ),
            ))
        if not rows:
            rows.append((None, ("-", "-", "Escribe una consulta arriba (/) para buscar")))
        if self._selected_rag_key not in self._rag_hits_by_key:
            self._selected_rag_key = next(iter(self._rag_hits_by_key), None)
        self._sync_table("#rag-results-table", rows, preserve_key=self._selected_rag_key)
        self._render_knowledge_detail()

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
                hdr = Text()
                hdr.append(f"{time.strftime('%H:%M:%S')}  ", style="#64748b")
                hdr.append("▸ ", style="bold #d9b15f")
                hdr.append(cmd_str, style="bold #f8fafc")
                rlog.write(hdr)
                rlog.write(Text(""))
            except NoMatches:
                pass
            self._push_event(LiveEvent(time.strftime("%H:%M:%S"), "info", "runner", f"Iniciado: {cmd_str}"))

        self.call_from_thread(_begin)

        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"  # keep our prints in order with child tool output
        env["FORCE_COLOR"] = "1"

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
