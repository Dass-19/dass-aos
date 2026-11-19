"""Cross-platform interactive PTY/ConPTY terminal emulator and Herdr-style screen detector.

Implements ADR-011 & CA-7:
- Pure-stdlib Windows ConPTY (`CreatePseudoConsole` / `ResizePseudoConsole` / `ClosePseudoConsole`
  with `STARTF_USESTDHANDLES` and `CREATE_UNICODE_ENVIRONMENT` stripping `CLAUDECODE`) and Unix `pty.openpty()`.
- 2D VT100/ANSI/TrueColor screen buffer (`VtScreen`) supporting cursor motion, erase ops, scroll
  regions (`DECSTBM`), alternate screen (`?1049h/l`), 16/256/24-bit RGB SGR colors, full ECMA-48
  CSI intermediate/final bytes, OSC 0/2 titles (with BEL or ST `\x1b\\`), and OSC 7501 status.
- Screen-manifest state detector (`detect_terminal_agent_state`) implementing Herdr's `claude.toml`
  and `agy.toml` rules (`running`, `pending`/`blocked`, `idle`).
- Interactive Textual widget (`AgentTerminalWidget`) with Terminal Mode (raw key forwarding to PTY)
  and Navigate Mode (`Ctrl+G` / `Ctrl+B` to return to TUI shortcuts).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

from rich.cells import cell_len
from rich.text import Text

try:
    from textual import events
    from textual.widgets import Static
except ImportError:  # pragma: no cover - allows importing pty_terminal without textual
    events = None  # type: ignore[assignment]
    Static = object  # type: ignore[assignment,misc]

_ANSI_16_FG = {
    30: "#1e293b", 31: "#f87171", 32: "#34d399", 33: "#fbbf24",
    34: "#60a5fa", 35: "#c084fc", 36: "#38bdf8", 37: "#e2e8f0",
    90: "#64748b", 91: "#fca5a5", 92: "#6ee7b7", 93: "#fde68a",
    94: "#93c5fd", 95: "#d8b4fe", 96: "#7dd3fc", 97: "#f8fafc",
}
_ANSI_16_BG = {code + 10: color for code, color in _ANSI_16_FG.items()}


def _xterm_256_to_hex(idx: int) -> str:
    idx = max(0, min(255, idx))
    if idx < 8:
        return _ANSI_16_FG.get(30 + idx, "#e2e8f0")
    if idx < 16:
        return _ANSI_16_FG.get(90 + (idx - 8), "#f8fafc")
    if idx < 232:
        n = idx - 16
        r = (n // 36) % 6
        g = (n // 6) % 6
        b = n % 6
        levels = (0, 95, 135, 175, 215, 255)
        return f"#{levels[r]:02x}{levels[g]:02x}{levels[b]:02x}"
    gray = 8 + (idx - 232) * 10
    return f"#{gray:02x}{gray:02x}{gray:02x}"


@dataclass
class VtCell:
    """Single character cell in the 2D terminal screen grid."""

    char: str = " "
    fg: str = ""
    bg: str = ""
    bold: bool = False
    dim: bool = False
    underline: bool = False
    reverse: bool = False

    def style_str(self, is_cursor: bool = False) -> str:
        parts: List[str] = []
        if self.bold or is_cursor:
            parts.append("bold")
        if self.dim:
            parts.append("dim")
        if self.underline:
            parts.append("underline")
        if is_cursor:
            parts.append("#060b11 on #d9b15f")
            return " ".join(parts)
        fg = self.bg if self.reverse else self.fg
        bg = self.fg if self.reverse else self.bg
        if fg:
            parts.append(fg)
        elif self.reverse:
            parts.append("#060b11")
        if bg:
            parts.append(f"on {bg}")
        elif self.reverse:
            parts.append("on #e2e8f0")
        return " ".join(parts)


_ESC_TOKEN_RE = re.compile(
    r"\x1b\]([^\x07\x1b]*)(?:\x07|\x1b\\)"                  # Group 1: OSC sequence (BEL or ST `\x1b\\`)
    r"|\x1b\[([\x30-\x3f]*)([\x20-\x2f]*)([\x40-\x7e])"     # Group 2, 3, 4: ECMA-48 CSI params, intermediates, final
    r"|\x1b([78cDEHMNOZ><=])"                               # Group 5: single-char ESC
    r"|\x1b[\(\)\*\+][0AB]"                                 # Charset designation (ignore)
    r"|\x1b[P_\^X][^\x1b]*\x1b\\"                           # DCS / APC / PM / SOS string sequences (ignore)
)


class VtScreen:
    """Pure-Python 2D VT100/ANSI/TrueColor screen state machine (`ADR-011`)."""

    def __init__(self, cols: int = 90, rows: int = 26) -> None:
        self.cols = max(20, int(cols))
        self.rows = max(6, int(rows))
        self.grid: List[List[VtCell]] = self._blank_grid(self.rows, self.cols)
        self._saved_grid: Optional[List[List[VtCell]]] = None
        self.scrollback: List[List[VtCell]] = []
        self.scroll_offset: int = 0
        self.mouse_tracking: bool = False
        self.cursor_row = 0
        self.cursor_col = 0
        self._saved_cursor = (0, 0)
        self._alt_saved_cursor = (0, 0)
        self._last_graphic_char = ""
        self.scroll_top = 0
        self.scroll_bottom = self.rows - 1
        self.cursor_visible = True
        self.osc_title = ""
        self.osc_state = ""
        self.version = 0
        self._partial = ""
        self._cur_style = VtCell()

    @property
    def alt_screen(self) -> bool:
        return self._saved_grid is not None

    def scroll_view(self, delta: int) -> bool:
        """Scroll viewport up (`delta > 0`) or down (`delta < 0`) through styled scrollback."""
        if not self.scrollback or self.alt_screen or delta == 0:
            return False
        new_off = max(0, min(len(self.scrollback), self.scroll_offset + int(delta)))
        if new_off == self.scroll_offset:
            return False
        self.scroll_offset = new_off
        self.version += 1
        return True

    def reset_scroll(self) -> None:
        if self.scroll_offset != 0:
            self.scroll_offset = 0
            self.version += 1

    @staticmethod
    def _blank_row(cols: int) -> List[VtCell]:
        return [VtCell() for _ in range(cols)]

    @classmethod
    def _blank_grid(cls, rows: int, cols: int) -> List[List[VtCell]]:
        return [cls._blank_row(cols) for _ in range(rows)]

    def resize(self, cols: int, rows: int) -> None:
        new_cols = max(20, int(cols))
        new_rows = max(6, int(rows))
        if new_cols == self.cols and new_rows == self.rows:
            return
        src_start = 0
        if new_rows < self.rows and self.cursor_row >= new_rows:
            src_start = min(self.rows - new_rows, max(0, self.cursor_row - new_rows + 1))
        new_grid = self._blank_grid(new_rows, new_cols)
        for r in range(min(self.rows - src_start, new_rows)):
            for c in range(min(self.cols, new_cols)):
                new_grid[r][c] = self.grid[src_start + r][c]
        if self._saved_grid is not None:
            saved_new = self._blank_grid(new_rows, new_cols)
            for r in range(min(len(self._saved_grid), new_rows)):
                for c in range(min(len(self._saved_grid[r]), new_cols)):
                    saved_new[r][c] = self._saved_grid[r][c]
            self._saved_grid = saved_new
        self.cols = new_cols
        self.rows = new_rows
        self.grid = new_grid
        self.scroll_top = 0
        self.scroll_bottom = self.rows - 1
        self.cursor_row = max(0, min(self.rows - 1, self.cursor_row - src_start))
        self.cursor_col = min(self.cols - 1, self.cursor_col)
        sr, sc = self._saved_cursor
        self._saved_cursor = (max(0, min(self.rows - 1, sr - src_start)), min(self.cols - 1, sc))
        self.scroll_offset = min(self.scroll_offset, len(self.scrollback))
        self.version += 1

    def feed(self, data: Union[str, bytes]) -> None:
        if isinstance(data, bytes):
            text = data.decode("utf-8", errors="replace")
        else:
            text = data
        if not text:
            return
        buf = self._partial + text
        self._partial = ""

        pos = 0
        for m in _ESC_TOKEN_RE.finditer(buf):
            if m.start() > pos:
                self._write_plain(buf[pos:m.start()])
            pos = m.end()
            osc, csi_params, csi_inter, csi_final, esc_single = m.groups()
            if osc is not None:
                self._handle_osc(osc)
            elif csi_final is not None:
                self._handle_csi(csi_params or "", csi_inter or "", csi_final)
            elif esc_single is not None:
                self._handle_esc_single(esc_single)

        if pos < len(buf):
            rem = buf[pos:]
            esc_idx = rem.find("\x1b")
            if esc_idx != -1:
                if esc_idx > 0:
                    self._write_plain(rem[:esc_idx])
                tail = rem[esc_idx:]
                if len(tail) < 512:
                    self._partial = tail
            else:
                self._write_plain(rem)
        self.version += 1

    def _scroll_up(self, count: int = 1, top: Optional[int] = None, bottom: Optional[int] = None) -> None:
        t = self.scroll_top if top is None else max(0, min(self.rows - 1, top))
        b = self.scroll_bottom if bottom is None else max(t, min(self.rows - 1, bottom))
        for _ in range(max(1, count)):
            if t == 0 and not self.alt_screen:
                row_copy = [
                    VtCell(c.char, c.fg, c.bg, c.bold, c.dim, c.underline, c.reverse)
                    for c in self.grid[0]
                ]
                while row_copy and row_copy[-1].char == " " and not row_copy[-1].bg:
                    row_copy.pop()
                if self.scrollback or any(c.char != " " for c in row_copy):
                    self.scrollback.append(row_copy)
                    if len(self.scrollback) > 1200:
                        self.scrollback = self.scrollback[-1200:]
            del self.grid[t]
            self.grid.insert(b, self._blank_row(self.cols))

    def _scroll_down(self, count: int = 1, top: Optional[int] = None, bottom: Optional[int] = None) -> None:
        t = self.scroll_top if top is None else max(0, min(self.rows - 1, top))
        b = self.scroll_bottom if bottom is None else max(t, min(self.rows - 1, bottom))
        for _ in range(max(1, count)):
            del self.grid[b]
            self.grid.insert(t, self._blank_row(self.cols))

    def _linefeed(self) -> None:
        if self.cursor_row == self.scroll_bottom:
            self._scroll_up(1, self.scroll_top, self.scroll_bottom)
        elif self.cursor_row + 1 < self.rows:
            self.cursor_row += 1

    def _write_plain(self, chunk: str) -> None:
        for ch in chunk:
            if ch == "\r":
                self.cursor_col = 0
            elif ch in ("\n", "\v", "\f"):
                self._linefeed()
            elif ch == "\b":
                self.cursor_col = max(0, self.cursor_col - 1)
            elif ch == "\t":
                next_tab = ((self.cursor_col // 8) + 1) * 8
                self.cursor_col = min(self.cols - 1, next_tab)
            elif ch == "\x07":
                continue
            elif ord(ch) >= 32:
                w = cell_len(ch)
                if w <= 0:
                    continue
                if w == 2 and self.cursor_col + 2 > self.cols:
                    self.cursor_col = 0
                    self._linefeed()
                elif self.cursor_col >= self.cols:
                    self.cursor_col = 0
                    self._linefeed()
                st = self._cur_style
                self.grid[self.cursor_row][self.cursor_col] = VtCell(
                    char=ch,
                    fg=st.fg,
                    bg=st.bg,
                    bold=st.bold,
                    dim=st.dim,
                    underline=st.underline,
                    reverse=st.reverse,
                )
                self._last_graphic_char = ch
                self.cursor_col += 1
                if w == 2 and self.cursor_col < self.cols:
                    self.grid[self.cursor_row][self.cursor_col] = VtCell(
                        char="",
                        fg=st.fg,
                        bg=st.bg,
                        bold=st.bold,
                        dim=st.dim,
                        underline=st.underline,
                        reverse=st.reverse,
                    )
                    self.cursor_col += 1

    def _handle_osc(self, osc: str) -> None:
        code, _, payload = osc.partition(";")
        if code in ("0", "2"):
            self.osc_title = payload.strip()
        elif code == "7501":
            for kv in payload.split(":"):
                k, _, v = kv.partition("=")
                if k.strip() == "state":
                    self.osc_state = v.strip().lower()

    def _handle_esc_single(self, ch: str) -> None:
        if ch == "7":
            self._saved_cursor = (self.cursor_row, self.cursor_col)
        elif ch == "8":
            sr, sc = self._saved_cursor
            self.cursor_row = max(0, min(self.rows - 1, sr))
            self.cursor_col = max(0, min(self.cols - 1, sc))
        elif ch == "M":
            if self.cursor_row == self.scroll_top:
                self._scroll_down(1, self.scroll_top, self.scroll_bottom)
            elif self.cursor_row > 0:
                self.cursor_row -= 1
        elif ch in ("D", "E"):
            if ch == "E":
                self.cursor_col = 0
            self._linefeed()
        elif ch == "c":
            self.grid = self._blank_grid(self.rows, self.cols)
            self.cursor_row = 0
            self.cursor_col = 0
            self.scroll_top = 0
            self.scroll_bottom = self.rows - 1
            self._cur_style = VtCell()

    def _handle_csi(self, params: str, inter: str, final: str) -> None:
        # Ignore sequences with intermediate bytes (e.g. DECSCUSR `\x1b[2 q`, DECSTR `\x1b[!p`)
        # or non-DEC private prefixes `<`, `=`, `>` (e.g. Kitty keyboard `\x1b[>1u`, `\x1b[<u`,
        # modifyOtherKeys `\x1b[>4;2m`) so they never mis-trigger `CSI u` (restore cursor -> 0,0) or SGR.
        if inter or (params and params[0] in "<=>"):
            return
        private = params.startswith("?")
        clean = params[1:] if private else params
        parts = [p.split(":", 1)[0] for p in clean.split(";")] if clean else ["0"]
        nums = [int(p) if p.isdigit() else 0 for p in parts]
        n0 = nums[0] if nums else 0

        if private:
            if final in ("h", "l"):
                enable = final == "h"
                for code in nums:
                    if code == 25:
                        self.cursor_visible = enable
                    elif code in (1000, 1002, 1003):
                        self.mouse_tracking = enable
                    elif code in (1049, 1047, 47):
                        if enable and self._saved_grid is None:
                            self._alt_saved_cursor = (self.cursor_row, self.cursor_col)
                            self._saved_grid = [list(r) for r in self.grid]
                            self.grid = self._blank_grid(self.rows, self.cols)
                            self.cursor_row = 0
                            self.cursor_col = 0
                            self.scroll_offset = 0
                        elif not enable and self._saved_grid is not None:
                            self.grid = self._saved_grid
                            self._saved_grid = None
                            sr, sc = self._alt_saved_cursor
                            self.cursor_row = max(0, min(self.rows - 1, sr))
                            self.cursor_col = max(0, min(self.cols - 1, sc))
            return

        if final in ("H", "f"):
            r = max(1, nums[0] if len(nums) >= 1 and nums[0] > 0 else 1) - 1
            c = max(1, nums[1] if len(nums) >= 2 and nums[1] > 0 else 1) - 1
            self.cursor_row = min(self.rows - 1, r)
            self.cursor_col = min(self.cols - 1, c)
        elif final == "A":
            self.cursor_row = max(0, self.cursor_row - max(1, n0))
        elif final in ("B", "e"):
            self.cursor_row = min(self.rows - 1, self.cursor_row + max(1, n0))
        elif final in ("C", "a"):
            self.cursor_col = min(self.cols - 1, self.cursor_col + max(1, n0))
        elif final == "D":
            self.cursor_col = max(0, self.cursor_col - max(1, n0))
        elif final == "E":
            self.cursor_row = min(self.rows - 1, self.cursor_row + max(1, n0))
            self.cursor_col = 0
        elif final == "F":
            self.cursor_row = max(0, self.cursor_row - max(1, n0))
            self.cursor_col = 0
        elif final in ("G", "`"):
            self.cursor_col = min(self.cols - 1, max(1, n0) - 1)
        elif final == "d":
            self.cursor_row = min(self.rows - 1, max(1, n0) - 1)
        elif final == "J":
            if n0 == 2:
                self.grid = self._blank_grid(self.rows, self.cols)
            elif n0 == 3:
                self.scrollback.clear()
            elif n0 == 0:
                for c in range(self.cursor_col, self.cols):
                    self.grid[self.cursor_row][c] = VtCell()
                for r in range(self.cursor_row + 1, self.rows):
                    self.grid[r] = self._blank_row(self.cols)
            elif n0 == 1:
                for r in range(0, self.cursor_row):
                    self.grid[r] = self._blank_row(self.cols)
                for c in range(0, min(self.cols, self.cursor_col + 1)):
                    self.grid[self.cursor_row][c] = VtCell()
        elif final == "K":
            row = self.grid[self.cursor_row]
            if n0 == 0:
                for c in range(self.cursor_col, self.cols):
                    row[c] = VtCell()
            elif n0 == 1:
                for c in range(0, min(self.cols, self.cursor_col + 1)):
                    row[c] = VtCell()
            elif n0 == 2:
                self.grid[self.cursor_row] = self._blank_row(self.cols)
        elif final == "L":
            self._scroll_down(max(1, n0), self.cursor_row, self.scroll_bottom)
        elif final == "M":
            self._scroll_up(max(1, n0), self.cursor_row, self.scroll_bottom)
        elif final == "P":
            cnt = max(1, n0)
            row = self.grid[self.cursor_row]
            del row[self.cursor_col:min(self.cols, self.cursor_col + cnt)]
            while len(row) < self.cols:
                row.append(VtCell())
        elif final == "@":
            cnt = max(1, n0)
            row = self.grid[self.cursor_row]
            for _ in range(cnt):
                row.insert(self.cursor_col, VtCell())
            del row[self.cols:]
        elif final == "X":
            cnt = max(1, n0)
            for c in range(self.cursor_col, min(self.cols, self.cursor_col + cnt)):
                self.grid[self.cursor_row][c] = VtCell()
        elif final == "S":
            self._scroll_up(max(1, n0), self.scroll_top, self.scroll_bottom)
        elif final == "T":
            self._scroll_down(max(1, n0), self.scroll_top, self.scroll_bottom)
        elif final == "r":
            top = max(1, nums[0] if len(nums) >= 1 and nums[0] > 0 else 1) - 1
            bot = max(1, nums[1] if len(nums) >= 2 and nums[1] > 0 else self.rows) - 1
            if 0 <= top < bot < self.rows:
                self.scroll_top = top
                self.scroll_bottom = bot
            else:
                self.scroll_top = 0
                self.scroll_bottom = self.rows - 1
            self.cursor_row = 0
            self.cursor_col = 0
        elif final == "s":
            self._saved_cursor = (self.cursor_row, self.cursor_col)
        elif final == "u":
            sr, sc = self._saved_cursor
            self.cursor_row = max(0, min(self.rows - 1, sr))
            self.cursor_col = max(0, min(self.cols - 1, sc))
        elif final == "b":
            if self._last_graphic_char:
                self._write_plain(self._last_graphic_char * min(self.cols, max(1, n0)))
        elif final == "m":
            self._apply_sgr(nums)

    def _apply_sgr(self, nums: List[int]) -> None:
        idx = 0
        st = self._cur_style
        while idx < len(nums):
            code = nums[idx]
            if code == 0:
                st = VtCell()
            elif code == 1:
                st.bold = True
            elif code == 2:
                st.dim = True
            elif code == 4:
                st.underline = True
            elif code == 7:
                st.reverse = True
            elif code == 22:
                st.bold = False
                st.dim = False
            elif code == 24:
                st.underline = False
            elif code == 27:
                st.reverse = False
            elif code == 39:
                st.fg = ""
            elif code == 49:
                st.bg = ""
            elif code in _ANSI_16_FG:
                st.fg = _ANSI_16_FG[code]
            elif code in _ANSI_16_BG:
                st.bg = _ANSI_16_BG[code]
            elif code in (38, 48):
                is_fg = code == 38
                if idx + 2 < len(nums) and nums[idx + 1] == 5:
                    hex_c = _xterm_256_to_hex(nums[idx + 2])
                    if is_fg:
                        st.fg = hex_c
                    else:
                        st.bg = hex_c
                    idx += 2
                elif idx + 4 < len(nums) and nums[idx + 1] == 2:
                    r = max(0, min(255, nums[idx + 2]))
                    g = max(0, min(255, nums[idx + 3]))
                    b = max(0, min(255, nums[idx + 4]))
                    hex_c = f"#{r:02x}{g:02x}{b:02x}"
                    if is_fg:
                        st.fg = hex_c
                    else:
                        st.bg = hex_c
                    idx += 4
            idx += 1
        self._cur_style = st

    def non_empty_lines(self, last_n: int = 12) -> List[str]:
        lines: List[str] = []
        for row in self.grid:
            s = "".join(c.char for c in row).rstrip()
            if s.strip():
                lines.append(s)
        return lines[-last_n:] if last_n > 0 else lines

    def plain_text(self) -> str:
        lines = ["".join(c.char for c in row).rstrip() for row in self.grid]
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)

    def render_rich(self, show_cursor: bool = True) -> Text:
        out = Text(no_wrap=True)
        if self.scroll_offset > 0 and self.scrollback and not self.alt_screen:
            combined = self.scrollback + self.grid
            end_idx = max(0, len(combined) - min(self.scroll_offset, len(self.scrollback)))
            start_idx = max(0, end_idx - self.rows)
            visible_rows = combined[start_idx:end_idx]
            while len(visible_rows) < self.rows:
                visible_rows = list(visible_rows) + [[]]
            cursor_active = False
        else:
            visible_rows = self.grid
            cursor_active = show_cursor and self.cursor_visible

        for r_idx, row in enumerate(visible_rows):
            run_chars: List[str] = []
            run_style = ""
            for c_idx, cell in enumerate(row[: self.cols]):
                is_cur = cursor_active and r_idx == self.cursor_row and c_idx == self.cursor_col
                st = cell.style_str(is_cursor=is_cur)
                if st != run_style and run_chars:
                    out.append("".join(run_chars), style=run_style or "#e2e8f0")
                    run_chars.clear()
                run_style = st
                run_chars.append(cell.char)
            if run_chars:
                trimmed = "".join(run_chars)
                if not run_style:
                    trimmed = trimmed.rstrip()
                if trimmed:
                    out.append(trimmed, style=run_style or "#e2e8f0")
            if r_idx < self.rows - 1:
                out.append("\n")
        return out


_OSC_SPINNER_RE = re.compile(r"^[\u2800-\u28ff\u25d0-\u25d3]\s")
_LINE_SPINNER_RE = re.compile(r"^\s*[\u2801-\u28ff*·\u2722\u2733\u2736\u273b\u273d⏸⏵]\s+\S")


def detect_terminal_agent_state(screen: VtScreen) -> Tuple[str, str]:
    """Classify live PTY screen state (`running`, `pending`, `idle`) using Herdr's rules (`CA-7`)."""
    if screen.osc_state == "blocked":
        return "pending", "Esperando confirmación en terminal (OSC 7501)"
    if screen.osc_state == "working":
        return "running", ""

    bottom = screen.non_empty_lines(12)
    bottom_lower = [ln.lower() for ln in bottom]
    joined = "\n".join(bottom_lower)

    # 1. Blocked / Pending rules from Herdr's `claude.toml` and `agy.toml`
    blocker_phrases = (
        "do you want to proceed?",
        "waiting for permission",
        "do you want to allow this connection?",
        "run a dynamic workflow?",
        "requests your input",
        "do you trust the contents of this project?",
        "import this conversation?",
    )
    for phrase in blocker_phrases:
        if phrase in joined:
            reason = next((ln.strip() for ln in bottom if "?" in ln or "bash" in ln.lower()), phrase)
            return "pending", reason[:90]

    if "esc to cancel" in joined and ("enter to confirm" in joined or "enter to select" in joined):
        reason = next((ln.strip() for ln in bottom if "?" in ln), "Formulario interactivo pendiente en terminal")
        return "pending", reason[:90]

    last_two = "\n".join(bottom_lower[-2:])
    if "navigate" in last_two and ("tab amend" in last_two or "esc skip" in last_two):
        reason = next((ln.strip() for ln in bottom[:-1] if ln.strip()), "Diálogo interactivo en terminal")
        return "pending", reason[:90]

    # 2. Working rules (`osc_title_working`, `live_turn_working`, `esc_cancel_footer_working`)
    if _OSC_SPINNER_RE.match(screen.osc_title):
        return "running", ""
    if "esc to interrupt" in joined or "signing in..." in joined or "loading conversations..." in joined:
        return "running", ""
    if any("waiting for " in ln and "background agent" in ln for ln in bottom_lower):
        return "running", ""
    if any(_LINE_SPINNER_RE.match(ln) and ("…" in ln or "..." in ln or "esc to" in ln.lower()) for ln in bottom):
        return "running", ""

    # 3. Idle rules (`live_prompt_box`, `osc_title_idle`, `agy ? for shortcuts`)
    if screen.osc_title.startswith("✳ ") or any(ln.lstrip().startswith(("❯", "> ")) for ln in bottom[-5:]):
        return "idle", ""
    if "? for shortcuts" in joined:
        return "idle", ""

    return "idle", ""


def _build_sanitized_pty_env() -> Dict[str, str]:
    env = os.environ.copy()
    for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT"):
        env.pop(k, None)
    env["TERM"] = "xterm-256color"
    env["COLORTERM"] = "truecolor"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


class PtySession:
    """Live OS pseudo-terminal session (`ConPTY` on Windows, `pty` on Unix) backed by `VtScreen`."""

    def __init__(
        self,
        session_key: str,
        command: Sequence[str],
        cwd: Path,
        cols: int = 90,
        rows: int = 26,
    ) -> None:
        self.session_key = session_key
        self.command = list(command)
        self.cwd = cwd.resolve()
        self.screen = VtScreen(cols=cols, rows=rows)
        self.alive = False
        self.user_interacted = False
        self.pid: Optional[int] = None
        self.exit_code: Optional[int] = None
        self._lock = threading.Lock()
        self._pending_chunks: List[bytes] = []

        # OS handles
        self._fd_in: Optional[int] = None
        self._fd_out: Optional[int] = None
        self._hpc: Optional[int] = None
        self._hproc: Optional[int] = None
        self._proc: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        if self.alive:
            return True
        if sys.platform == "win32":
            ok = self._start_win_conpty()
        else:
            ok = self._start_unix_pty()
        if ok:
            self.alive = True
            self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self._reader_thread.start()
        return ok

    def _start_win_conpty(self) -> bool:
        import ctypes
        import ctypes.wintypes as wt
        import msvcrt

        k32 = ctypes.windll.kernel32

        class STARTUPINFOW(ctypes.Structure):
            _fields_ = [
                ("cb", wt.DWORD), ("lpReserved", wt.LPWSTR), ("lpDesktop", wt.LPWSTR), ("lpTitle", wt.LPWSTR),
                ("dwX", wt.DWORD), ("dwY", wt.DWORD), ("dwXSize", wt.DWORD), ("dwYSize", wt.DWORD),
                ("dwXCountChars", wt.DWORD), ("dwYCountChars", wt.DWORD), ("dwFillAttribute", wt.DWORD),
                ("dwFlags", wt.DWORD), ("wShowWindow", wt.WORD), ("cbReserved2", wt.WORD),
                ("lpReserved2", ctypes.POINTER(wt.BYTE)), ("hStdInput", wt.HANDLE),
                ("hStdOutput", wt.HANDLE), ("hStdError", wt.HANDLE),
            ]

        class STARTUPINFOEXW(ctypes.Structure):
            _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]

        class PROCESS_INFORMATION(ctypes.Structure):
            _fields_ = [("hProcess", wt.HANDLE), ("hThread", wt.HANDLE), ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD)]

        k32.CreatePseudoConsole.argtypes = [wt.DWORD, wt.HANDLE, wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.HANDLE)]
        k32.CreatePseudoConsole.restype = ctypes.c_long
        k32.InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, wt.DWORD, wt.DWORD, ctypes.POINTER(ctypes.c_size_t)]
        k32.InitializeProcThreadAttributeList.restype = wt.BOOL
        k32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
        k32.UpdateProcThreadAttribute.argtypes = [
            ctypes.c_void_p, wt.DWORD, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p
        ]
        k32.UpdateProcThreadAttribute.restype = wt.BOOL
        k32.CreateProcessW.argtypes = [
            wt.LPCWSTR, wt.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wt.BOOL, wt.DWORD,
            ctypes.c_void_p, wt.LPCWSTR, ctypes.POINTER(STARTUPINFOEXW), ctypes.POINTER(PROCESS_INFORMATION),
        ]
        k32.CreateProcessW.restype = wt.BOOL

        hpc = wt.HANDLE()
        h_in_r, h_in_w = wt.HANDLE(), wt.HANDLE()
        h_out_r, h_out_w = wt.HANDLE(), wt.HANDLE()
        if not k32.CreatePipe(ctypes.byref(h_in_r), ctypes.byref(h_in_w), None, 0):
            return False
        if not k32.CreatePipe(ctypes.byref(h_out_r), ctypes.byref(h_out_w), None, 0):
            k32.CloseHandle(h_in_r)
            k32.CloseHandle(h_in_w)
            return False

        coord_packed = (self.screen.rows << 16) | (self.screen.cols & 0xFFFF)
        if k32.CreatePseudoConsole(coord_packed, h_in_r, h_out_w, 0, ctypes.byref(hpc)) != 0:
            for h in (h_in_r, h_in_w, h_out_r, h_out_w):
                k32.CloseHandle(h)
            return False

        size = ctypes.c_size_t(0)
        k32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        self._attr_buf = (ctypes.c_byte * size.value)()
        k32.InitializeProcThreadAttributeList(self._attr_buf, 1, 0, ctypes.byref(size))
        k32.UpdateProcThreadAttribute(
            self._attr_buf,
            0,
            0x00020016,  # PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE
            ctypes.c_void_p(hpc.value),
            ctypes.sizeof(wt.HANDLE),
            None,
            None,
        )

        si = STARTUPINFOEXW()
        si.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
        # STARTF_USESTDHANDLES (0x100) with NULL handles prevents inheriting parent pipes
        si.StartupInfo.dwFlags = 0x00000100
        si.lpAttributeList = ctypes.cast(self._attr_buf, ctypes.c_void_p)
        pi = PROCESS_INFORMATION()

        env_dict = _build_sanitized_pty_env()
        env_block_str = "".join(f"{k}={v}\0" for k, v in env_dict.items()) + "\0"
        env_buf = ctypes.create_unicode_buffer(env_block_str)

        cmd_line = subprocess.list2cmdline(self.command)
        cmd_buf = ctypes.create_unicode_buffer(cmd_line)
        ok = k32.CreateProcessW(
            None,
            cmd_buf,
            None,
            None,
            False,
            0x00080000 | 0x00000400,  # EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT
            ctypes.cast(env_buf, ctypes.c_void_p),
            str(self.cwd),
            ctypes.byref(si),
            ctypes.byref(pi),
        )
        k32.DeleteProcThreadAttributeList(self._attr_buf)
        k32.CloseHandle(h_in_r)
        k32.CloseHandle(h_out_w)
        if not ok:
            k32.ClosePseudoConsole(hpc)
            k32.CloseHandle(h_in_w)
            k32.CloseHandle(h_out_r)
            return False

        k32.CloseHandle(pi.hThread)
        self._hpc = int(hpc.value)
        self._hproc = int(pi.hProcess)
        self.pid = int(pi.dwProcessId)
        self._fd_in = msvcrt.open_osfhandle(int(h_in_w.value), os.O_WRONLY)
        self._fd_out = msvcrt.open_osfhandle(int(h_out_r.value), os.O_RDONLY)
        return True

    def _start_unix_pty(self) -> bool:
        import fcntl
        import pty
        import struct
        import termios

        master_fd, slave_fd = pty.openpty()
        winsz = struct.pack("HHHH", self.screen.rows, self.screen.cols, 0, 0)
        try:
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsz)
        except OSError:
            pass
        env = _build_sanitized_pty_env()
        try:
            self._proc = subprocess.Popen(
                self.command,
                cwd=str(self.cwd),
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=env,
                close_fds=True,
            )
        except OSError:
            os.close(master_fd)
            os.close(slave_fd)
            return False
        os.close(slave_fd)
        self.pid = self._proc.pid
        self._fd_in = master_fd
        self._fd_out = master_fd
        return True

    def _reader_loop(self) -> None:
        fd = self._fd_out
        if fd is None:
            return
        while self.alive:
            try:
                chunk = os.read(fd, 8192)
                if not chunk:
                    break
                with self._lock:
                    self._pending_chunks.append(chunk)
            except OSError:
                break
        self.alive = False

    def check_alive(self) -> bool:
        """Check if the OS child process is still running; close ConPTY when it exits (`H4`)."""
        if not self.alive:
            return False
        if sys.platform == "win32" and self._hproc is not None:
            import ctypes
            import ctypes.wintypes as wt

            k32 = ctypes.windll.kernel32
            k32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
            k32.WaitForSingleObject.restype = wt.DWORD
            res = k32.WaitForSingleObject(wt.HANDLE(self._hproc), 0)
            if res != 0x00000102:  # not WAIT_TIMEOUT -> child exited
                code = wt.DWORD(0)
                k32.GetExitCodeProcess(wt.HANDLE(self._hproc), ctypes.byref(code))
                self.exit_code = int(code.value)
                self.alive = False
                if self._hpc is not None:
                    hpc_val = self._hpc
                    self._hpc = None
                    try:
                        k32.ClosePseudoConsole(wt.HANDLE(hpc_val))
                    except Exception:
                        pass
                return False
        elif self._proc is not None:
            rc = self._proc.poll()
            if rc is not None:
                self.exit_code = rc
                self.alive = False
                return False
        return True

    def poll_output(self) -> bool:
        """Drain newly read PTY bytes into `self.screen` and update liveness. Returns True if screen updated."""
        was_alive = self.alive
        self.check_alive()
        with self._lock:
            chunks = list(self._pending_chunks)
            self._pending_chunks.clear()
        if chunks:
            self.screen.feed(b"".join(chunks))
            return True
        return was_alive != self.alive

    def write(self, data: Union[str, bytes], mark_user: bool = True) -> bool:
        if not self.alive or self._fd_in is None:
            return False
        if mark_user:
            self.user_interacted = True
        raw = data.encode("utf-8", errors="replace") if isinstance(data, str) else data
        try:
            os.write(self._fd_in, raw)
            return True
        except OSError:
            return False

    def resize(self, cols: int, rows: int) -> None:
        cols = max(20, int(cols))
        rows = max(6, int(rows))
        if cols == self.screen.cols and rows == self.screen.rows:
            return
        self.screen.resize(cols, rows)
        if not self.alive:
            return
        if sys.platform == "win32" and self._hpc is not None:
            import ctypes
            import ctypes.wintypes as wt

            k32 = ctypes.windll.kernel32
            k32.ResizePseudoConsole.argtypes = [wt.HANDLE, wt.DWORD]
            coord_packed = (rows << 16) | (cols & 0xFFFF)
            try:
                k32.ResizePseudoConsole(wt.HANDLE(self._hpc), coord_packed)
            except OSError:
                pass
        elif self._fd_out is not None:
            try:
                import fcntl
                import struct
                import termios

                winsz = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(self._fd_out, termios.TIOCSWINSZ, winsz)
            except OSError:
                pass

    def stop(self) -> None:
        self.alive = False
        if sys.platform == "win32":
            import ctypes
            import ctypes.wintypes as wt

            k32 = ctypes.windll.kernel32
            if self._hpc is not None:
                hpc_val = self._hpc
                self._hpc = None
                try:
                    k32.ClosePseudoConsole(wt.HANDLE(hpc_val))
                except Exception:
                    pass
            if self._hproc is not None:
                hproc_val = self._hproc
                self._hproc = None
                try:
                    k32.TerminateProcess(wt.HANDLE(hproc_val), 0)
                    k32.CloseHandle(wt.HANDLE(hproc_val))
                except Exception:
                    pass
        elif self._proc is not None:
            proc = self._proc
            self._proc = None
            try:
                proc.terminate()
                proc.wait(timeout=0.5)
            except Exception:
                pass

        if self._reader_thread is not None and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=0.2)

        unique_fds = {self._fd_in, self._fd_out} - {None}
        self._fd_in = None
        self._fd_out = None
        for fd in unique_fds:
            try:
                os.close(fd)  # type: ignore[arg-type]
            except OSError:
                pass


_KEY_ESCAPE_MAP: Dict[str, str] = {
    "enter": "\r",
    "return": "\r",
    "tab": "\t",
    "shift+tab": "\x1b[Z",
    "backspace": "\x7f",
    "escape": "\x1b",
    "up": "\x1b[A",
    "down": "\x1b[B",
    "right": "\x1b[C",
    "left": "\x1b[D",
    "home": "\x1b[H",
    "end": "\x1b[F",
    "delete": "\x1b[3~",
    "pageup": "\x1b[5~",
    "pagedown": "\x1b[6~",
    "space": " ",
    "ctrl+c": "\x03",
    "ctrl+d": "\x04",
    "ctrl+z": "\x1a",
    "ctrl+l": "\x0c",
    "ctrl+u": "\x15",
    "ctrl+w": "\x17",
    "ctrl+a": "\x01",
    "ctrl+e": "\x05",
    "ctrl+o": "\x0f",
    "f1": "\x1bOP",
    "f2": "\x1bOQ",
    "f3": "\x1bOR",
    "f4": "\x1bOS",
    "f5": "\x1b[15~",
    "f6": "\x1b[17~",
    "f7": "\x1b[18~",
    "f8": "\x1b[19~",
    "f9": "\x1b[20~",
    "f11": "\x1b[23~",
    "f12": "\x1b[24~",
}


def encode_terminal_key(key: str, character: Optional[str] = None) -> str:
    """Convert a Textual key event into raw VT100 input bytes for the PTY."""
    k = key.lower()
    if k in _KEY_ESCAPE_MAP:
        return _KEY_ESCAPE_MAP[k]
    if character and len(character) == 1 and ord(character) >= 32:
        return character
    return ""


class AgentTerminalWidget(Static):
    """Focusable live PTY terminal viewport widget for `aos tui` Tab 3 (`CA-7`).

    When focused (**Modo Terminal**), all keystrokes go directly to the attached PTY
    session (`claude`, `powershell`, etc.) without leaking to `AosTuiApp.BINDINGS`.
    Pressing `Ctrl+G` or `Ctrl+B` leaves Modo Terminal back to **Modo Navegación**.
    """

    can_focus = True

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.pty_session: Optional[PtySession] = None
        self._last_render_sig: Optional[Tuple[int, int, int, int, int, bool]] = None
        self._space_hold_start = 0.0
        self._space_last = 0.0
        self._voice_latch_timer = None

    # Hold-to-talk latch: terminals have no key-up, so CLI hold mode reads auto-repeat.
    # After VOICE_LATCH_SECS of continuous space we keep feeding the repeat ourselves.
    VOICE_LATCH_SECS = 3.0
    _REPEAT_GAP = 0.6  # > OS initial auto-repeat delay (~500 ms)

    def _voice_latched(self) -> bool:
        return self._voice_latch_timer is not None

    def _release_voice_latch(self) -> None:
        if self._voice_latch_timer is not None:
            self._voice_latch_timer.stop()
            self._voice_latch_timer = None
        self._space_hold_start = 0.0

    def _feed_space(self) -> None:
        if self.pty_session is None or not self.pty_session.alive:
            self._release_voice_latch()
            return
        self.pty_session.write(" ")

    def _handle_space_hold(self) -> bool:
        """Return True when the space press was consumed by the latch logic."""
        now = time.monotonic()
        repeating = now - self._space_last < self._REPEAT_GAP
        self._space_last = now
        if self._voice_latched():
            if repeating:
                return True  # finger still down; the timer is already feeding repeats
            self._release_voice_latch()  # fresh press → stop listening
            if hasattr(self.app, "notify"):
                self.app.notify("Escucha liberada", timeout=1.5)
            return True
        if not repeating:
            self._space_hold_start = now
            return False
        if now - self._space_hold_start < self.VOICE_LATCH_SECS:
            return False
        allowed = getattr(self.app, "voice_hold_latch_allowed", None)
        if not (callable(allowed) and allowed()):
            return False
        self._voice_latch_timer = self.set_interval(0.05, self._feed_space)
        if hasattr(self.app, "notify"):
            self.app.notify("🎤 Escuchando fijo · suelta y pulsa Espacio para terminar", timeout=3.0)
        return True

    def attach_pty(self, pty_session: Optional[PtySession]) -> None:
        self._release_voice_latch()
        self.pty_session = pty_session
        self._last_render_sig = None
        self.refresh_viewport(force=True)

    def _is_active_screen(self) -> bool:
        try:
            app_ref = self.app
            if app_ref is not None and self.screen is not app_ref.screen:
                return False
        except Exception:
            pass
        return True

    def on_resize(self, _event) -> None:
        if self._is_active_screen():
            self.refresh_viewport(force=True)

    def on_mouse_down(self, event) -> None:
        self.focus()
        event.stop()

    def _update_scroll_subtitle(
        self,
        scroll_offset: int,
        alive: bool = True,
        exit_code: Optional[int] = None,
    ) -> None:
        parent = getattr(self, "parent", None)
        if parent is None or not hasattr(parent, "border_subtitle"):
            return
        if not alive:
            code_s = f"código {exit_code}" if exit_code is not None else "cerrado"
            parent.border_subtitle = f"[bold #fbbf24]✕ Proceso finalizado ({code_s}) · Enter reconectar · Stop cerrar[/]"
        elif scroll_offset > 0:
            parent.border_subtitle = f"[bold #fbbf24]↑ SCROLL (-{scroll_offset} líneas · rueda / End para volver)[/]"
        else:
            parent.border_subtitle = None

    def _handle_mouse_scroll(self, direction: int, lines: int = 3) -> None:
        """Scroll chat history either via local `scrollback` or in-app `PageUp`/`PageDown` (`alt_screen`)."""
        sess = self.pty_session
        if sess is None:
            return
        scr = sess.screen
        if scr.alt_screen:
            if sess.alive:
                if scr.mouse_tracking:
                    sess.write("\x1b[5~" if direction < 0 else "\x1b[6~", mark_user=True)
                else:
                    seq = "\x1b[A" if direction < 0 else "\x1b[B"
                    sess.write(seq * max(1, min(lines, 3)), mark_user=True)
                self.refresh_viewport(force=True)
            return
        delta = lines if direction < 0 else -lines
        if scr.scroll_view(delta):
            self.refresh_viewport(force=True)

    def on_mouse_scroll_up(self, event) -> None:
        self._handle_mouse_scroll(-1, 3)
        event.stop()

    def on_mouse_scroll_down(self, event) -> None:
        self._handle_mouse_scroll(1, 3)
        event.stop()

    def refresh_viewport(self, force: bool = False) -> None:
        if not self._is_active_screen():
            return
        sess = self.pty_session
        if sess is None:
            self._last_render_sig = None
            self._update_scroll_subtitle(0)
            hint = Text()
            hint.append("Terminal de Agente (estilo Herdr)\n\n", style="bold #d9b15f")
            hint.append(
                "• Pulsa Enter sobre cualquier sesión de la izquierda (o clic en 'CLI') "
                "para abrir su consola interactiva real en vivo dentro de este panel.\n",
                style="#cbd5e1",
            )
            hint.append(
                "• Cuando el terminal esté enfocado (MODO TERMINAL), todo lo que teclees "
                "(↑/↓, Enter, 1, 2, /voice, Esc) se envía directo al CLI del agente.\n",
                style="#94a3b8",
            )
            hint.append(
                "• Usa la rueda del ratón o PgUp/PgDn para scrollear · Ctrl+Z (o F10) para pantalla completa · Ctrl+G para Modo Navegación.",
                style="#8aa8cc",
            )
            self.update(hint)
            return

        w = self.size.width
        h = self.size.height
        cw = self.content_size.width if self.content_size.width > 0 else max(0, w - 2)
        ch = self.content_size.height if self.content_size.height > 0 else max(0, h)
        if cw > 24 and ch > 6:
            sess.resize(cols=max(40, cw), rows=max(6, ch))
        sess.poll_output()
        sig = (id(sess), sess.screen.version, sess.screen.scroll_offset, cw, ch, sess.alive)
        if not force and sig == self._last_render_sig:
            return
        self._last_render_sig = sig
        rendered = sess.screen.render_rich(show_cursor=sess.alive)
        self._update_scroll_subtitle(
            sess.screen.scroll_offset,
            alive=sess.alive,
            exit_code=sess.exit_code,
        )
        if getattr(self, "is_mounted", True):
            self.update(rendered)

    def on_key(self, event) -> None:
        key = event.key.lower()
        event.stop()
        event.prevent_default()

        # Direct fullscreen toggle works even while typing inside Modo Terminal (no Ctrl+G needed)
        # Ctrl+Z is the reliable one on Windows: Alt+Z often arrives as Esc + "z".
        if key in ("ctrl+z", "alt+z", "meta+z", "f10"):
            if getattr(self, "id", "") == "zoom-terminal-pane" and hasattr(self.screen, "dismiss"):
                self.screen.dismiss(None)
                return
            if hasattr(self.app, "action_toggle_zoom"):
                self.app.action_toggle_zoom()
            return

        if key in ("ctrl+g", "ctrl+b"):
            if getattr(self, "id", "") == "zoom-terminal-pane" and hasattr(self.screen, "dismiss"):
                self.screen.dismiss("nav")  # leave fullscreen AND Modo Terminal
                return
            if hasattr(self.app, "set_focus"):
                self.app.set_focus(None)
            if hasattr(self.app, "notify"):
                self.app.notify("Modo Navegación activo (clic o Enter en terminal para volver a teclear)", timeout=2.0)
            return

        if self.pty_session is None or not self.pty_session.alive:
            if key in ("enter", "return") and hasattr(self.app, "action_attach_agent_pty"):
                self.app.action_attach_agent_pty()
            elif key == "z" and hasattr(self.app, "action_toggle_zoom"):
                self.app.action_toggle_zoom()
            return

        scr = self.pty_session.screen
        if not scr.alt_screen and (scr.scrollback or scr.scroll_offset > 0):
            page_step = max(3, scr.rows - 2)
            if key == "shift+pageup" or (key == "pageup" and scr.scrollback):
                if scr.scroll_view(page_step):
                    self.refresh_viewport(force=True)
                return
            if key == "shift+pagedown" or (key == "pagedown" and scr.scroll_offset > 0):
                if scr.scroll_view(-page_step):
                    self.refresh_viewport(force=True)
                return
            if key == "shift+up":
                if scr.scroll_view(2):
                    self.refresh_viewport(force=True)
                return
            if key == "shift+down" and scr.scroll_offset > 0:
                if scr.scroll_view(-2):
                    self.refresh_viewport(force=True)
                return
            if key in ("end", "ctrl+end") and scr.scroll_offset > 0:
                scr.reset_scroll()
                self.refresh_viewport(force=True)
                return

        if scr.scroll_offset > 0:
            scr.reset_scroll()

        if key == "space":
            if self._handle_space_hold():
                return
        elif self._voice_latched():
            self._release_voice_latch()

        seq = encode_terminal_key(key, getattr(event, "character", None))
        if seq:
            self.pty_session.write(seq)
            if hasattr(self, "set_timer"):
                self.set_timer(0.015, lambda: self.refresh_viewport(force=True))
            else:
                self.refresh_viewport(force=True)
