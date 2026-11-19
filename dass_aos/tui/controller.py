"""Interactive session controller, pending alert dispatcher, and TTS/voice bridge for `aos tui`.

Implements CA-4 (pending alerts with sound + OS toast + mute), CA-5 (Herdr-style
session creation, prompt streaming, and process termination), and CA-6 (native `/voice`
delegation with automatic OS TTS spoken responses).
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Sequence, Set, Tuple

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


DEFAULT_TTS_VOICE = "es-CO-SalomeNeural"
DEFAULT_TTS_RATE = "+25%"

_VOICE_ALIASES: Dict[str, str] = {
    "salome": "es-CO-SalomeNeural",
    "salomé": "es-CO-SalomeNeural",
    "gonzalo": "es-CO-GonzaloNeural",
}

_EDGE_TTS_PLAY_SCRIPT = r"""
import asyncio, ctypes, os, shutil, subprocess, sys, tempfile

def _fallback_os_tts(text: str, voice: str, sapi_rate: int) -> None:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["AOS_TTS_TEXT"] = text
    env["AOS_TTS_VOICE"] = voice
    env["AOS_TTS_SAPI_RATE"] = str(sapi_rate)
    if sys.platform == "win32":
        ps_cmd = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.Rate = [int]$env:AOS_TTS_SAPI_RATE; "
            "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Name -like ('*' + $env:AOS_TTS_VOICE + '*') } | Select-Object -First 1; "
            "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }; "
            "$s.Speak($env:AOS_TTS_TEXT)"
        )
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd], env=env, check=False)
    elif sys.platform == "darwin":
        subprocess.run(["say", "-r", str(max(120, min(320, 175 + sapi_rate * 22))), "--", text], env=env, check=False)
    else:
        subprocess.run(["spd-say", "-r", str(max(-100, min(100, sapi_rate * 12))), "--", text], env=env, check=False)

def _play_mp3(path: str) -> bool:
    if sys.platform == "win32":
        winmm = ctypes.windll.winmm
        alias = f"aos_tts_{os.getpid()}"
        buf = ctypes.create_unicode_buffer(256)
        rc = winmm.mciSendStringW(f'open "{path}" type mpegvideo alias {alias}', buf, 256, 0)
        if rc != 0:
            return False
        try:
            rc = winmm.mciSendStringW(f"play {alias} wait", buf, 256, 0)
            return rc == 0
        finally:
            winmm.mciSendStringW(f"close {alias}", buf, 256, 0)
    if sys.platform == "darwin" and shutil.which("afplay"):
        return subprocess.run(["afplay", path], check=False).returncode == 0
    for player, args in (("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet", path]), ("mpg123", ["-q", path])):
        if shutil.which(player):
            return subprocess.run([player, *args], check=False).returncode == 0
    return False

text = os.environ.get("AOS_TTS_TEXT", "")
voice = os.environ.get("AOS_TTS_VOICE", "es-CO-SalomeNeural")
rate = os.environ.get("AOS_TTS_RATE", "+25%")
sapi_rate = int(os.environ.get("AOS_TTS_SAPI_RATE", "2"))
if not text.strip():
    sys.exit(0)

tmp_path = None
try:
    import edge_tts
    fd, tmp_path = tempfile.mkstemp(prefix="aos_tts_", suffix=".mp3")
    os.close(fd)
    asyncio.run(edge_tts.Communicate(text, voice=voice, rate=rate).save(tmp_path))
    if not os.path.isfile(tmp_path) or os.path.getsize(tmp_path) < 128 or not _play_mp3(tmp_path):
        _fallback_os_tts(text, voice, sapi_rate)
except Exception:
    _fallback_os_tts(text, voice, sapi_rate)
finally:
    if tmp_path and os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except OSError:
            pass
""".strip()


def normalize_tts_voice(raw: Optional[str]) -> str:
    """Resolve friendly voice aliases (e.g. `Salome`) to Edge neural voice IDs."""
    text = (raw or "").strip()
    if not text:
        return DEFAULT_TTS_VOICE
    return _VOICE_ALIASES.get(text.lower(), text)


def normalize_tts_rate(raw: Optional[str]) -> str:
    """Normalize speed strings (`+25%`, `0.25+`, `+0.25`, `-10%`) to Edge TTS rate syntax."""
    text = (raw or "").strip()
    if not text:
        return DEFAULT_TTS_RATE
    if re.fullmatch(r"[+-]?\d+%", text):
        return text if text[0] in "+-" else f"+{text}"
    m_trail = re.fullmatch(r"(\d+(?:\.\d+)?)([+-])", text)
    if m_trail:
        val = float(m_trail.group(1))
        sign = m_trail.group(2)
        pct = int(round(val * 100)) if val <= 3.0 else int(round(val))
        return f"{sign}{pct}%"
    try:
        val = float(text)
    except ValueError:
        return DEFAULT_TTS_RATE
    pct = int(round(val * 100)) if abs(val) <= 3.0 else int(round(val))
    return f"{pct:+d}%"


def _rate_to_sapi5(rate: str) -> int:
    """Convert percentage rate (e.g. `+25%`) to Windows SAPI5 SpeechSynthesizer.Rate (-10..10)."""
    m = re.fullmatch(r"([+-]?\d+)%", (rate or "").strip())
    if not m:
        return 2
    pct = int(m.group(1))
    # ~12.5% per SAPI5 step (+25% -> +2)
    return max(-10, min(10, int(round(pct / 12.5))))


class TTSManager:
    """OS/Edge-TTS speech synthesizer with FIFO queue so agent responses play in order (`CA-6`)."""

    def __init__(self, voice: Optional[str] = None, rate: Optional[str] = None) -> None:
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None
        self._queue: Deque[str] = deque()
        self.last_spoken: str = ""
        self._current_text: str = ""
        self.voice: str = normalize_tts_voice(voice if voice is not None else os.environ.get("AOS_TTS_VOICE"))
        self.rate: str = normalize_tts_rate(rate if rate is not None else os.environ.get("AOS_TTS_RATE"))

    @property
    def queue_size(self) -> int:
        with self._lock:
            return len(self._queue)

    @property
    def is_speaking(self) -> bool:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return True
            return bool(self._queue)

    def poll(self) -> bool:
        """Advance FIFO queue if current utterance finished; return True while speaking."""
        with self._lock:
            if self._proc is not None and self._proc.poll() is not None:
                self._proc = None
                self._current_text = ""
            if self._proc is None and self._queue:
                self._start_next_locked()
            return (self._proc is not None and self._proc.poll() is None) or bool(self._queue)

    def stop(self) -> bool:
        """Immediately stop any active speech output and clear queued responses (`Esc`, `m`, `Stop`)."""
        with self._lock:
            had_queued = bool(self._queue)
            self._queue.clear()
            proc = self._proc
            self._proc = None
            self._current_text = ""
        stopped = False
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                stopped = True
            except OSError:
                pass
        return stopped or had_queued

    @staticmethod
    def _has_edge_tts() -> bool:
        return importlib.util.find_spec("edge_tts") is not None

    @classmethod
    def _build_tts_command(
        cls,
        cleaned: str,
        voice: str = DEFAULT_TTS_VOICE,
        rate: str = DEFAULT_TTS_RATE,
    ) -> Tuple[List[str], Dict[str, str]]:
        norm_voice = normalize_tts_voice(voice)
        norm_rate = normalize_tts_rate(rate)
        sapi_rate = _rate_to_sapi5(norm_rate)
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["AOS_TTS_TEXT"] = cleaned
        env["AOS_TTS_VOICE"] = norm_voice
        env["AOS_TTS_RATE"] = norm_rate
        env["AOS_TTS_SAPI_RATE"] = str(sapi_rate)
        if cls._has_edge_tts():
            return [sys.executable, "-c", _EDGE_TTS_PLAY_SCRIPT], env
        if sys.platform == "win32":
            ps_cmd = (
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "$s.Rate = [int]$env:AOS_TTS_SAPI_RATE; "
                "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Name -like ('*' + $env:AOS_TTS_VOICE + '*') } | Select-Object -First 1; "
                "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }; "
                "$s.Speak($env:AOS_TTS_TEXT)"
            )
            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd]
        elif sys.platform == "darwin":
            wpm = max(120, min(320, 175 + sapi_rate * 22))
            cmd = ["say", "-r", str(wpm), "--", cleaned]
        else:
            spd_rate = max(-100, min(100, sapi_rate * 12))
            cmd = ["spd-say", "-r", str(spd_rate), "--", cleaned]
        return cmd, env

    def _spawn_process(self, cleaned: str) -> Optional[subprocess.Popen]:
        cmd, env = self._build_tts_command(cleaned, voice=self.voice, rate=self.rate)
        try:
            return subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
        except OSError:
            return None

    def _watch_process(self, proc: subprocess.Popen) -> None:
        try:
            proc.wait()
        except Exception:
            pass
        with self._lock:
            if self._proc is proc:
                self._proc = None
                self._current_text = ""
                if self._queue:
                    self._start_next_locked()

    def _start_next_locked(self) -> bool:
        while self._queue:
            nxt = self._queue.popleft()
            proc = self._spawn_process(nxt)
            if proc is None:
                continue
            self._proc = proc
            self._current_text = nxt
            self.last_spoken = nxt
            threading.Thread(target=self._watch_process, args=(proc,), daemon=True).start()
            return True
        return False

    def speak(self, raw_text: str, *, interrupt: bool = False) -> bool:
        """Queue conversational text in FIFO order for OS TTS synthesis (or interrupt if requested)."""
        cleaned = clean_speech_text(raw_text)
        if not cleaned:
            return False
        if interrupt:
            self.stop()
        with self._lock:
            if self._proc is not None and self._proc.poll() is not None:
                self._proc = None
                self._current_text = ""
            # Avoid duplicate consecutive utterances
            if cleaned == self._current_text or (self._queue and self._queue[-1] == cleaned):
                return True
            self._queue.append(cleaned)
            if self._proc is None:
                return self._start_next_locked()
            return True

    def synthesize_to_wav(self, raw_text: str, output_path: Path) -> bool:
        """Synthesize cleaned speech text to a WAV audio file (useful for offline audio verification)."""
        cleaned = clean_speech_text(raw_text)
        if not cleaned:
            return False
        out = output_path.resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["AOS_TTS_TEXT"] = cleaned
        env["AOS_TTS_WAV"] = str(out)
        env["AOS_TTS_VOICE"] = self.voice
        env["AOS_TTS_RATE"] = self.rate
        env["AOS_TTS_SAPI_RATE"] = str(_rate_to_sapi5(self.rate))
        if sys.platform == "win32":
            ps_cmd = (
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "$s.Rate = [int]$env:AOS_TTS_SAPI_RATE; "
                "$s.SetOutputToWaveFile($env:AOS_TTS_WAV); "
                "$s.Speak($env:AOS_TTS_TEXT); "
                "$s.Dispose()"
            )
            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd]
        elif sys.platform == "darwin":
            cmd = ["say", "-o", str(out), "--data-format=LEI16@22050", "--", cleaned]
        else:
            return False
        try:
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, timeout=20)
            return res.returncode == 0 and out.is_file() and out.stat().st_size > 44
        except (OSError, subprocess.SubprocessError):
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
        self._voice_opted_out: Set[str] = set()
        self._spoken_by_session: Dict[str, str] = {}
        self._last_telemetry_voice: Dict[str, bool] = {}
        self.active_proc: Optional[subprocess.Popen] = None
        self.active_session_key: Optional[str] = None
        self.named_sessions: Dict[str, AgentSessionInfo] = {}
        self.pty_sessions: Dict[str, PtySession] = {}
        self.recently_closed_ptys: List[Tuple[str, Optional[int]]] = []

    def has_agy_cli_db(self, session_id: str) -> bool:
        """Return True if `session_id` exists in the `antigravity-cli` local store."""
        return (self.antigravity_cli_home / "conversations" / f"{session_id}.db").is_file()

    def is_agy_ide_session_open_in_ide(self, session_id: str) -> bool:
        """Return True if the IDE session currently has an active SQLite WAL file open in Antigravity 2.0."""
        ide_home = self.antigravity_cli_home.parent / "antigravity"
        return (ide_home / "conversations" / f"{session_id}.db-wal").is_file()

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

        # 5. Select row and confirm native `[Import this conversation? (y/n)]` fork-import,
        # unless the IDE session currently has an active WAL open in Antigravity 2.0 (parallel collision guard).
        pty_sess.write("\r", mark_user=False)
        if _wait_for(lambda txt: "import this conversation" in txt.lower(), timeout=3.0):
            if pty_sess.alive and not pty_sess.user_interacted:
                if self.is_agy_ide_session_open_in_ide(sess.session_id):
                    pty_sess.screen.feed(
                        "\r\n\x1b[1;33m⚠ Sesión abierta en Antigravity 2.0 (WAL activo): "
                        "auto-import pausado para evitar colisión en paralelo. Pulsa 'y' o 'n'.\x1b[0m\r\n"
                    )
                else:
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
        self._voice_opted_out.discard(session_key)
        self.voice_sessions.add(session_key)

    def toggle_voice(self, session_key: str, *, currently_active: Optional[bool] = None) -> bool:
        was_on = currently_active if currently_active is not None else (session_key in self.voice_sessions)
        if was_on:
            self.voice_sessions.discard(session_key)
            self._voice_opted_out.add(session_key)
            self.tts.stop()
            return False
        self._voice_opted_out.discard(session_key)
        self.voice_sessions.add(session_key)
        return True

    def is_voice_enabled(self, session_key: str, *, telemetry_voice_active: bool = False) -> bool:
        if session_key in self._voice_opted_out:
            return False
        return (session_key in self.voice_sessions) or telemetry_voice_active

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
        """Enqueue latest assistant responses in FIFO order for all sessions with `/voice` active (`CA-6`)."""
        last_enqueued: Optional[str] = None
        for sess in sessions:
            key = f"{sess.tool}:{sess.session_id}"
            # A `/voice` typed straight in the CLI overrides the button's last choice.
            if self._last_telemetry_voice.get(key) not in (None, sess.voice_active):
                self._voice_opted_out.discard(key)
                if not sess.voice_active:
                    self.voice_sessions.discard(key)
            self._last_telemetry_voice[key] = sess.voice_active
            if sess.voice_active and key not in self._voice_opted_out:
                self.voice_sessions.add(key)
            if key not in self.voice_sessions or key in self._voice_opted_out:
                continue
            text = (sess.last_assistant_text or sess.pending_reason or "").strip()
            if not text:
                continue
            if self._spoken_by_session.get(key) == text:
                continue
            self._spoken_by_session[key] = text
            if self.tts.speak(text):
                last_enqueued = text
        return last_enqueued

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
