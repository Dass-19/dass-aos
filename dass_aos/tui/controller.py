"""Interactive session controller, pending alert dispatcher, and TTS/voice bridge for `aos tui`.

Implements CA-4 (pending alerts with sound + OS toast + mute), CA-5 (Herdr-style
session creation, prompt streaming, and process termination), and CA-6 (native `/voice`
delegation with automatic OS TTS spoken responses).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from ..telemetry import AgentSessionInfo
from .pty_terminal import PtySession, detect_terminal_agent_state

_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_DIFF_LINE_RE = re.compile(r"^(?:@@\s.*|diff --git\s.*|\+\+\+\s.*|---\s.*|[+-][^\s+-].*)$")
_MD_DECOR_RE = re.compile(r"[*_`#~>]+")


def clean_speech_text(raw: str, max_chars: int = 700) -> str:
    """Extract clean conversational text and questions for TTS, stripping code blocks and diffs."""
    if not raw or not raw.strip():
        return ""
    text = _CODE_FENCE_RE.sub(" ", raw)
    text = _MD_LINK_RE.sub(r"\1", text)
    kept_lines: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _DIFF_LINE_RE.match(stripped):
            continue
        if stripped.startswith(("$ ", "▶ ", "╭", "╰", "│")):
            continue
        cleaned_line = _MD_DECOR_RE.sub("", stripped).strip()
        if cleaned_line:
            kept_lines.append(cleaned_line)
    joined = " ".join(" ".join(kept_lines).split())
    if len(joined) > max_chars:
        joined = joined[:max_chars].rsplit(" ", 1)[0] + "..."
    return joined


class TTSManager:
    """Zero-dependency OS speech synthesizer that speaks agent responses when `/voice` is active."""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self.last_spoken: str = ""

    @property
    def is_speaking(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self) -> bool:
        """Immediately stop any active speech output (`Esc` or new turn)."""
        proc = self._proc
        self._proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                return True
            except OSError:
                pass
        return False

    def speak(self, raw_text: str) -> bool:
        """Synthesize conversational text asynchronously using the host OS TTS engine."""
        cleaned = clean_speech_text(raw_text)
        if not cleaned:
            return False
        self.stop()
        self.last_spoken = cleaned

        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["AOS_TTS_TEXT"] = cleaned

        if sys.platform == "win32":
            ps_cmd = (
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "$s.Speak($env:AOS_TTS_TEXT)"
            )
            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd]
        elif sys.platform == "darwin":
            cmd = ["say", "--", cleaned]
        else:
            cmd = ["spd-say", "--", cleaned]

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
            return True
        except OSError:
            self._proc = None
            return False


class AlertDispatcher:
    """Multi-channel alert dispatcher for sessions entering `pending` state (`CA-4`)."""

    def __init__(self, muted: bool = False) -> None:
        self.muted = muted
        self._active_pending: Dict[str, str] = {}

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        return self.muted

    def process_sessions(self, sessions: Sequence[AgentSessionInfo]) -> List[AgentSessionInfo]:
        """Return sessions that newly transitioned to `pending` (or changed reason) and fire alerts."""
        current_keys: Set[str] = set()
        newly_pending: List[AgentSessionInfo] = []

        for sess in sessions:
            key = f"{sess.tool}:{sess.session_id}"
            if sess.status == "pending":
                current_keys.add(key)
                reason = sess.pending_reason or "Esperando acción del usuario"
                if self._active_pending.get(key) != reason:
                    self._active_pending[key] = reason
                    newly_pending.append(sess)
                    if not self.muted:
                        self.play_sound()
                        self.send_os_toast(
                            f"DASS-AOS · {sess.tool} en PENDING",
                            f"{sess.title}: {reason}",
                        )

        # Clear sessions that left pending state
        for old_key in list(self._active_pending):
            if old_key not in current_keys:
                del self._active_pending[old_key]

        return newly_pending

    def play_sound(self) -> None:
        """Emit an audible alert via `winsound` on Windows or terminal bell fallback."""
        if sys.platform == "win32":
            try:
                import winsound

                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                return
            except Exception:
                pass
        try:
            sys.stdout.write("\a")
            sys.stdout.flush()
        except OSError:
            pass

    def send_os_toast(self, title: str, message: str) -> None:
        """Trigger a non-blocking native desktop notification."""
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["AOS_ALERT_TITLE"] = title[:80]
        env["AOS_ALERT_MSG"] = message[:200]

        if sys.platform == "win32":
            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "Add-Type -AssemblyName System.Drawing; "
                "$n = New-Object System.Windows.Forms.NotifyIcon; "
                "$n.Icon = [System.Drawing.SystemIcons]::Warning; "
                "$n.BalloonTipTitle = $env:AOS_ALERT_TITLE; "
                "$n.BalloonTipText = $env:AOS_ALERT_MSG; "
                "$n.Visible = $true; "
                "$n.ShowBalloonTip(4000); "
                "Start-Sleep -Milliseconds 4200; "
                "$n.Dispose()"
            )
            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_script]
        elif sys.platform == "darwin":
            cmd = [
                "osascript",
                "-e",
                'display notification (system attribute "AOS_ALERT_MSG") with title (system attribute "AOS_ALERT_TITLE")',
            ]
        else:
            cmd = ["notify-send", "--", title[:80], message[:200]]

        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
        except OSError:
            pass


class SessionController:
    """Herdr-style session manager for creating, resuming, prompting, and stopping agent sessions (`CA-5`, `CA-6`)."""

    def __init__(
        self,
        project_root: Path,
        tts: Optional[TTSManager] = None,
        antigravity_cli_home: Optional[Path] = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.tts = tts if tts is not None else TTSManager()
        self.antigravity_cli_home = (
            antigravity_cli_home
            if antigravity_cli_home is not None
            else (Path.home() / ".gemini" / "antigravity-cli")
        )
        self.voice_sessions: Set[str] = set()
        self._spoken_by_session: Dict[str, str] = {}
        self.active_proc: Optional[subprocess.Popen] = None
        self.active_session_key: Optional[str] = None
        self.named_sessions: Dict[str, AgentSessionInfo] = {}
        self.pty_sessions: Dict[str, PtySession] = {}
        self.recently_closed_ptys: List[Tuple[str, Optional[int]]] = []

    def has_agy_cli_db(self, session_id: str) -> bool:
        """Return True if `session_id` exists in the `antigravity-cli` local store."""
        return (self.antigravity_cli_home / "conversations" / f"{session_id}.db").is_file()

    def needs_agy_ide_import(self, sess: AgentSessionInfo) -> bool:
        """Return True if an `antigravity` IDE session is not yet in `antigravity-cli`."""
        if sess.tool != "antigravity" or sess.meta == "nueva (TUI)":
            return False
        if self.has_agy_cli_db(sess.session_id) or "agy-cli" in sess.meta:
            return False
        return True

    def check_cli_availability(self, tool: str) -> Dict[str, Any]:
        """Check whether the interactive CLI binary for `tool` is installed in PATH."""
        is_win = sys.platform == "win32"
        if tool == "claude-code":
            binary = "claude"
            display_name = "Claude Code CLI"
            install_display = (
                "irm https://claude.ai/install.ps1 | iex"
                if is_win
                else "curl -fsSL https://claude.ai/install.sh | bash"
            )
            login_hint = "Tras instalar, ejecuta `claude` e inicia sesión con tu cuenta de Anthropic."
            docs_url = "https://docs.anthropic.com/en/docs/claude-code"
        else:
            binary = "agy"
            display_name = "Antigravity CLI"
            install_display = (
                "irm https://antigravity.google/cli/install.ps1 | iex"
                if is_win
                else "curl -fsSL https://antigravity.google/cli/install.sh | bash"
            )
            login_hint = "Tras instalar, ejecuta `agy` e inicia sesión con tu cuenta de Google."
            docs_url = "https://antigravity.google/docs/cli/reference"

        exe = shutil.which(binary)
        if is_win:
            ps = shutil.which("powershell") or "powershell.exe"
            install_argv = [
                ps,
                "-NoLogo",
                "-NoExit",
                "-Command",
                f"{install_display}; Write-Host ''; Write-Host 'Instalación finalizada. {login_hint}' -ForegroundColor Cyan",
            ]
            shell_argv = [ps, "-NoLogo"]
        else:
            shell = os.environ.get("SHELL") or "/bin/bash"
            install_argv = [
                "bash",
                "-lc",
                f"{install_display}; echo ''; echo 'Instalación finalizada. {login_hint}'; exec {shell}",
            ]
            shell_argv = [shell]

        return {
            "tool": tool,
            "binary": binary,
            "display_name": display_name,
            "installed": bool(exe),
            "executable": exe or "",
            "install_display": install_display,
            "install_argv": install_argv,
            "shell_argv": shell_argv,
            "login_hint": login_hint,
            "docs_url": docs_url,
        }

    def build_interactive_cli_command(self, sess: AgentSessionInfo) -> List[str]:
        """Build the interactive CLI command to run inside a live PTY pane (`ADR-011`)."""
        if sess.tool == "claude-code":
            exe = shutil.which("claude") or "claude"
            if sess.meta == "nueva (TUI)":
                args = ["--session-id", sess.session_id, "-n", sess.title]
            else:
                args = ["--resume", sess.session_id]
            if sys.platform == "win32" and exe.lower().endswith((".cmd", ".bat")):
                comspec = os.environ.get("COMSPEC", "cmd.exe")
                return [comspec, "/d", "/s", "/c", exe, *args]
            return [exe, *args]
        if sess.tool == "antigravity":
            exe = shutil.which("agy")
            if exe:
                if sess.meta == "nueva (TUI)" or self.needs_agy_ide_import(sess):
                    return [exe]
                return [exe, "--conversation", sess.session_id]
        if sys.platform == "win32":
            return [shutil.which("powershell") or "powershell.exe", "-NoLogo"]
        return [os.environ.get("SHELL") or "/bin/sh"]

    def _auto_open_agy_ide_session(self, pty_sess: PtySession, sess: AgentSessionInfo) -> None:
        """Drive `agy`'s native `/resume -> Other` picker to import and open an IDE session (`CA-7`)."""
        def _wait_for(pred, timeout: float = 12.0) -> bool:
            deadline = time.time() + timeout
            while time.time() < deadline:
                if not pty_sess.alive or pty_sess.user_interacted:
                    return False
                pty_sess.poll_output()
                if pred(pty_sess.screen.plain_text()):
                    return True
                time.sleep(0.15)
            return False

        # 1. Wait until `agy` finishes signing in and renders its interactive prompt footer
        if not _wait_for(lambda txt: "? for shortcuts" in txt.lower(), timeout=18.0):
            return
        time.sleep(0.25)

        # 2. Open `/resume` conversation picker (`CLI` tab opens first with `f2 Rename`)
        pty_sess.write("/resume", mark_user=False)
        time.sleep(0.45)
        if not pty_sess.alive or pty_sess.user_interacted:
            return
        pty_sess.write("\r", mark_user=False)

        if not _wait_for(
            lambda txt: "tab switch tab" in txt.lower() and "loading conversations" not in txt.lower(),
            timeout=10.0,
        ):
            return

        # 3. Switch to `Other` tab (`f2 Rename` only appears on the `CLI` tab)
        time.sleep(0.15)
        pty_sess.write("\t", mark_user=False)
        if not _wait_for(
            lambda txt: "tab switch tab" in txt.lower()
            and "f2 rename" not in txt.lower()
            and ("steps" in txt.lower() or "no conversations" in txt.lower()),
            timeout=3.0,
        ):
            if not pty_sess.alive or pty_sess.user_interacted:
                return
            pty_sess.write("\t", mark_user=False)
            if not _wait_for(
                lambda txt: "tab switch tab" in txt.lower()
                and "f2 rename" not in txt.lower()
                and ("steps" in txt.lower() or "no conversations" in txt.lower()),
                timeout=4.0,
            ):
                return

        # 4. Search by IDE summary title (exact match from conversation_summaries.db) or prompt title
        raw_query = (sess.summary_title or sess.title or "").lstrip("↳ ").strip()
        query = " ".join(raw_query.split())
        if not query or query == sess.session_id[:12]:
            return
        query = query[:48]
        time.sleep(0.15)
        pty_sess.write(query, mark_user=False)
        _wait_for(lambda txt: "search:" in txt.lower(), timeout=2.5)
        time.sleep(0.35)
        if not pty_sess.alive or pty_sess.user_interacted:
            return
        pty_sess.poll_output()
        filtered = pty_sess.screen.plain_text()
        if "no conversations available" in filtered.lower():
            # Reset search so the full `Other` list stays ready for manual selection
            pty_sess.write("\x1b", mark_user=False)
            return

        step_rows = re.findall(r"\b\d+\s+steps?\b", filtered.lower())
        if not step_rows:
            return
        if len(step_rows) > 1 and not (sess.summary_title and query.lower() == sess.summary_title.lower()[:len(query)]):
            # Multiple similar candidates: keep filtered list open for user disambiguation
            return

        # 5. Select row and confirm native `[Import this conversation? (y/n)]` fork-import
        pty_sess.write("\r", mark_user=False)
        if _wait_for(lambda txt: "import this conversation" in txt.lower(), timeout=3.0):
            if pty_sess.alive and not pty_sess.user_interacted:
                pty_sess.write("y", mark_user=False)

    def open_or_attach_pty(
        self,
        sess: AgentSessionInfo,
        cols: int = 90,
        rows: int = 26,
        command_override: Optional[Sequence[str]] = None,
    ) -> PtySession:
        """Return an existing live `PtySession` for `sess`, or spawn a new one (`CA-7`)."""
        skey = f"{sess.tool}:{sess.session_id}"
        existing = self.pty_sessions.get(skey)
        if existing is not None:
            if existing.alive:
                return existing
            existing.stop()
        cmd = list(command_override) if command_override is not None else self.build_interactive_cli_command(sess)
        cwd = Path(sess.cwd) if sess.cwd and Path(sess.cwd).is_dir() else self.project_root
        pty_sess = PtySession(session_key=skey, command=cmd, cwd=cwd, cols=cols, rows=rows)
        needs_agy_auto_import = (
            command_override is None
            and sess.tool == "antigravity"
            and bool(shutil.which("agy"))
            and self.needs_agy_ide_import(sess)
        )
        if needs_agy_auto_import:
            pty_sess.screen.feed(
                f"\x1b[1;36m◆ Abriendo Antigravity CLI y cargando sesión IDE: {sess.summary_title or sess.title}\x1b[0m\r\n"
            )
        pty_sess.start()
        if needs_agy_auto_import and pty_sess.alive:
            threading.Thread(
                target=self._auto_open_agy_ide_session,
                args=(pty_sess, sess),
                daemon=True,
            ).start()
        if sess.meta == "nueva (TUI)":
            sess.meta = "activa (PTY)"
        self.pty_sessions[skey] = pty_sess
        return pty_sess

    def poll_all_ptys(self, sessions_by_key: Dict[str, AgentSessionInfo]) -> bool:
        """Poll all live PTY sessions, auto-close finished exit-0 sessions, and update screen states."""
        any_changed = False
        for skey, pty_sess in list(self.pty_sessions.items()):
            updated = pty_sess.poll_output()
            if updated:
                any_changed = True
            sess = sessions_by_key.get(skey)
            if not pty_sess.alive:
                if pty_sess.exit_code in (None, 0):
                    pty_sess.stop()
                    self.pty_sessions.pop(skey, None)
                    self.recently_closed_ptys.append((skey, pty_sess.exit_code))
                    if sess is not None:
                        sess.status = "idle"
                        sess.pending_reason = ""
                    any_changed = True
                elif sess is not None and sess.status in ("running", "pending"):
                    sess.status = "idle"
                    sess.pending_reason = ""
                    any_changed = True
                continue
            if sess is not None:
                prev_state = (sess.status, sess.pending_reason)
                st, reason = detect_terminal_agent_state(pty_sess.screen)
                if st == "pending":
                    sess.status = "pending"
                    sess.pending_reason = reason or "Esperando acción en terminal"
                elif st == "running":
                    sess.status = "running"
                    sess.pending_reason = ""
                else:
                    sess.status = "active"
                    sess.pending_reason = ""
                if (sess.status, sess.pending_reason) != prev_state:
                    any_changed = True
        return any_changed

    def enable_voice(self, session_key: str) -> None:
        self.voice_sessions.add(session_key)

    def toggle_voice(self, session_key: str) -> bool:
        if session_key in self.voice_sessions:
            self.voice_sessions.remove(session_key)
            self.tts.stop()
            return False
        self.voice_sessions.add(session_key)
        return True

    def is_voice_enabled(self, session_key: str) -> bool:
        return session_key in self.voice_sessions

    def create_named_session(self, name: str, tool: str = "claude-code") -> AgentSessionInfo:
        """Create a new tracked session with a Herdr-style slug name."""
        import time

        slug = re.sub(r"[^A-Za-z0-9_-]", "-", name.strip()) or f"session-{int(time.time()) % 10000}"
        sid = str(uuid.uuid4())
        sess = AgentSessionInfo(
            tool=tool,
            session_id=sid,
            title=slug,
            status="idle",
            cwd=str(self.project_root),
            updated_at=time.time(),
            meta="nueva (TUI)",
        )
        self.named_sessions[f"{tool}:{sid}"] = sess
        return sess

    def build_prompt_command(
        self,
        tool: str,
        prompt: str,
        session_id: Optional[str] = None,
        session_name: Optional[str] = None,
        resume: bool = False,
    ) -> List[str]:
        """Build the CLI command to send a prompt or resume an agent session."""
        clean_prompt = prompt.strip()
        if tool == "claude-code":
            cmd = ["claude"]
            if resume and session_id:
                cmd.extend(["--resume", session_id])
            elif session_id:
                cmd.extend(["--session-id", session_id])
            if session_name:
                cmd.extend(["-n", session_name])
            cmd.extend(["-p", clean_prompt, "--output-format", "stream-json", "--verbose"])
            return cmd
        cmd = ["agy"]
        if resume and session_id:
            cmd.extend(["--conversation", session_id])
        cmd.extend(["-p", clean_prompt, "--output-format", "stream-json"])
        return cmd

    def parse_stream_json_line(self, raw_line: str) -> Tuple[List[str], Optional[str]]:
        """Parse a `claude --output-format stream-json` line into display lines and assistant text."""
        stripped = raw_line.strip()
        if not stripped:
            return [], None
        try:
            obj: Any = json.loads(stripped)
        except ValueError:
            return [stripped], None
        if not isinstance(obj, dict):
            return [stripped], None

        ev_type = obj.get("type", "")
        display: List[str] = []
        assistant_text: Optional[str] = None

        if ev_type == "assistant":
            msg = obj.get("message") or {}
            content = msg.get("content") if isinstance(msg, dict) else None
            if isinstance(content, list):
                for blk in content:
                    if not isinstance(blk, dict):
                        continue
                    btype = blk.get("type")
                    if btype == "text" and blk.get("text"):
                        txt = str(blk["text"]).strip()
                        if txt:
                            assistant_text = txt
                            for ln in txt.splitlines():
                                display.append(f"💬 {ln}")
                    elif btype == "tool_use":
                        tname = str(blk.get("name") or "tool")
                        inp = blk.get("input") or {}
                        arg_preview = ""
                        if isinstance(inp, dict):
                            arg_preview = str(
                                inp.get("command")
                                or inp.get("file_path")
                                or inp.get("description")
                                or inp.get("skill")
                                or ""
                            )[:60]
                        display.append(f"▸ {tname}" + (f"  {arg_preview}" if arg_preview else ""))
        elif ev_type == "result":
            res_txt = str(obj.get("result") or "").strip()
            cost = obj.get("total_cost_usd")
            dur = obj.get("duration_ms")
            if res_txt:
                assistant_text = res_txt
            meta = []
            if isinstance(dur, (int, float)):
                meta.append(f"{dur / 1000.0:.1f}s")
            if isinstance(cost, (int, float)):
                meta.append(f"${cost:.3f}")
            suffix = f" ({' · '.join(meta)})" if meta else ""
            display.append(f"✓ Turno completado{suffix}")
        elif ev_type == "system" and obj.get("subtype"):
            display.append(f"• [{obj.get('subtype')}]")

        return display, assistant_text

    def sync_voice_sessions(self, sessions: Sequence[AgentSessionInfo]) -> Optional[str]:
        """Speak the latest assistant response for any session with `/voice` active (`CA-6`)."""
        for sess in sessions:
            key = f"{sess.tool}:{sess.session_id}"
            if sess.voice_active:
                self.voice_sessions.add(key)
            if key not in self.voice_sessions:
                continue
            text = (sess.last_assistant_text or sess.pending_reason or "").strip()
            if not text:
                continue
            if self._spoken_by_session.get(key) == text:
                continue
            self._spoken_by_session[key] = text
            if self.tts.speak(text):
                return text
        return None

    def stop_active_process(self, session_key: Optional[str] = None) -> bool:
        """Terminate the currently running managed session subprocess or PTY (`k`)."""
        stopped = False
        if session_key and session_key in self.pty_sessions:
            pty_s = self.pty_sessions.pop(session_key)
            pty_s.stop()
            stopped = True
        elif not session_key and self.pty_sessions:
            for k, pty_s in list(self.pty_sessions.items()):
                pty_s.stop()
                self.pty_sessions.pop(k, None)
                stopped = True
        proc = self.active_proc
        self.active_proc = None
        self.active_session_key = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                stopped = True
            except OSError:
                pass
        return stopped
