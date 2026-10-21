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
def dim(t: str) -> str: return style("90", t)
def italic(t: str) -> str: return style("3", t)
def cyan(t: str) -> str: return style("36", t)
def green(t: str) -> str: return style("32", t)
def yellow(t: str) -> str: return style("33", t)
def red(t: str) -> str: return style("31", t)
def magenta(t: str) -> str: return style("35", t)
def blue(t: str) -> str: return style("34", t)


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
    return cyan(bold(f"ℹ {text}"))


def badge_pass(text: str = "PASSED") -> str:
    return green(bold(f"✓ {text}"))


def badge_fail(text: str = "FAILED") -> str:
    return red(bold(f"✖ {text}"))


def badge_skip(text: str = "SKIPPED") -> str:
    return dim(f"· {text}")


class Card:
    """Helper to build consistent rounded terminal card boxes."""

    def __init__(self, title: str, subtitle: Optional[str] = None, width: int = 74):
        self.width = width
        self.lines: List[str] = []

        banner = f" DASS-AOS · {title} "
        if subtitle:
            banner = f" DASS-AOS · {title} ({subtitle}) "
        dashes = max(self.width - plain_len(banner) - 4, 4)
        self.lines.append(f"{cyan('╭──')}{bold(banner)}{cyan('─' * dashes + '╮')}")

    def line(self, text: str = "") -> Card:
        self.lines.append(f"{cyan('│')}  {text}")
        return self

    def field(self, label: str, value: str, label_width: int = 12) -> Card:
        pad = " " * max(label_width - len(label), 0)
        self.lines.append(f"{cyan('│')}  {dim(label + ':')}{pad} {value}")
        return self

    def empty(self) -> Card:
        self.lines.append(f"{cyan('│')}")
        return self

    def divider(self) -> Card:
        self.lines.append(f"{cyan('├' + '─' * (self.width - 2) + '┤')}")
        return self

    def render(self) -> str:
        dashes = self.width - 2
        out = list(self.lines)
        out.append(f"{cyan('╰' + '─' * dashes + '╯')}")
        return "\n".join(out)
