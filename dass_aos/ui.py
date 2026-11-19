"""Terminal UI styling and box formatting for DASS-AOS."""
from __future__ import annotations

import os
import re
import sys
from typing import List, Optional

from .constants import configure_utf8_output

configure_utf8_output()

ESC = "\033["
RESET = f"{ESC}0m"
ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def is_color_enabled() -> bool:
    """Detect if terminal supports ANSI colors and user hasn't opted out."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR") in ("1", "true", "yes"):
        return True
    return (
        sys.stdout.isatty()
        or os.environ.get("TERM") in ("xterm", "xterm-256color", "alacritty", "screen")
        or os.environ.get("WT_SESSION") is not None
        or "ANSICON" in os.environ
    )


USE_COLOR = is_color_enabled()


def style(code: str, text: str) -> str:
    return f"{ESC}{code}m{text}{RESET}" if USE_COLOR else text


def bold(t: str) -> str: return style("1", t)
def dim(t: str) -> str: return style("38;2;148;163;184", t)
def italic(t: str) -> str: return style("3", t)
def cyan(t: str) -> str: return style("38;2;138;168;204", t)
def green(t: str) -> str: return style("38;2;52;211;153", t)
def yellow(t: str) -> str: return style("38;2;217;177;95", t)
def red(t: str) -> str: return style("38;2;248;113;113", t)
def magenta(t: str) -> str: return style("38;2;167;139;250", t)
def blue(t: str) -> str: return style("38;2;83;113;149", t)


def _border(t: str) -> str:
    return style("38;2;83;113;149", t)


def plain_len(text: str) -> int:
    """Length of string without ANSI escape sequences."""
    return len(ANSI_RE.sub("", text))


def make_progress_bar(done: int, total: int, width: int = 24) -> str:
    """Generate a clean visual progress bar."""
    if total <= 0:
        return ""
    pct = done / total
    filled = int(round(width * pct))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {done}/{total} ({int(pct * 100)}%)"


def badge_error(text: str = "ERROR") -> str:
    return red(bold(f"✖ {text}"))


def badge_warn(text: str = "WARN") -> str:
    return yellow(bold(f"▲ {text}"))


def badge_info(text: str = "INFO") -> str:
    return cyan(bold(f"● {text}"))


def badge_pass(text: str = "PASSED") -> str:
    return green(bold(f"✓ {text}"))


def badge_fail(text: str = "FAILED") -> str:
    return red(bold(f"✖ {text}"))


def badge_skip(text: str = "SKIPPED") -> str:
    return dim(f"· {text}")


class Card:
    """Helper to build clean, auto-sized left-rail terminal cards matching the DASS-AOS palette."""

    def __init__(self, title: str, subtitle: Optional[str] = None, width: int = 72):
        self.title = title
        self.subtitle = subtitle
        self.width = width
        self._entries: List[tuple] = []

    def line(self, text: str = "") -> Card:
        self._entries.append(("line", text))
        return self

    def field(self, label: str, value: str, label_width: int = 13) -> Card:
        pad = " " * max(label_width - len(label), 1)
        self._entries.append(("line", f"{dim(label + ':')}{pad}{value}"))
        return self

    def empty(self) -> Card:
        self._entries.append(("empty", ""))
        return self

    def divider(self) -> Card:
        self._entries.append(("divider", ""))
        return self

    def render(self) -> str:
        header_plain = f" ◆ DASS-AOS · {self.title} " + (f"({self.subtitle}) " if self.subtitle else "")
        max_line = max(
            [plain_len(header_plain) + 4]
            + [plain_len(txt) + 4 for kind, txt in self._entries if kind == "line"]
        )
        rule_w = max(self.width, min(max_line, 96))

        banner = f" {yellow('◆')} {bold(f'DASS-AOS · {self.title}')}"
        if self.subtitle:
            banner += f" {dim(f'({self.subtitle})')}"
        banner += " "
        top_dashes = max(rule_w - plain_len(banner) - 3, 4)

        out: List[str] = [f"{_border('╭─')}{banner}{_border('─' * top_dashes)}"]
        for kind, txt in self._entries:
            if kind == "empty":
                out.append(_border("│"))
            elif kind == "divider":
                out.append(_border("├─" + "─" * max(rule_w - 2, 4)))
            else:
                out.append(f"{_border('│')}  {txt}")
        out.append(_border("╰" + "─" * max(rule_w - 1, 4)))
        return "\n".join(out)
