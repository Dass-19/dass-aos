"""Formatting helpers and Rich renderables for DASS-AOS TUI."""
from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from typing import Iterable, Optional, Sequence

from rich.text import Text

from ..status import CHECKING, NEEDS_DECISION, READY, WORKING
from ..telemetry import AgentSessionInfo, LiveEvent, TelemetrySnapshot


def format_tokens_compact(n: int) -> str:
    """Format token counts compactly (e.g. 842, 17.6k, 1.45M)."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def token_bar(part: int, total: int, width: int = 10, color: str = "#8aa8cc") -> Text:
    """Render a compact proportional usage bar."""
    t = Text(no_wrap=True)
    if total <= 0:
        t.append("█" * width, style="#1e293b")
        return t
    ratio = max(0.0, min(1.0, part / total))
    filled = max(1 if part > 0 else 0, int(round(width * ratio)))
    t.append("█" * filled, style=color)
    t.append("█" * (width - filled), style="#1e293b")
    return t


def _clip(text: str, limit: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[: max(1, limit - 1)] + "…"


# 9x8 pixel glyphs; each terminal cell shows two pixel rows via half blocks.
_GLYPHS = {
    "D": ("########.", "#########", "###...###", "###...###", "###...###", "###...###", "#########", "########."),
    "A": ("..#####..", ".#######.", "###...###", "###...###", "#########", "#########", "###...###", "###...###"),
    "S": (".########", "#########", "###......", "########.", ".########", "......###", "#########", "########."),
}
_WHITE = "#f8fafc"
_BAR_COLORS = ("#b89146", "#537195", "#844747", "#5b635d")  # ochre, slate blue, terracotta, olive
_BRAND_LIGHT = ("#d9b15f", "#8aa8cc", "#c46a6a", "#9aa59c")  # same hues, readable as text


def _logo_pixels() -> list:
    """12x52 pixel grid of colors (None = background): content, black gap, white rounded frame."""
    content = []
    for y in range(8):
        bar = [_BAR_COLORS[y // 2]] * 8  # 2px per bar; drawn as ▇ so a sliver separates them
        letters = [_WHITE if ch == "#" else None for ch in ".".join(_GLYPHS[c][y] for c in "DASS")]
        content.append(bar + [None] + letters)
    w = len(content[0]) + 4

    def side(inner):
        return [_WHITE, None] + inner + [None, _WHITE]

    frame = [None] + [_WHITE] * (w - 2) + [None]  # corners dropped = rounded
    gap = side([None] * (w - 4))
    return [frame, gap, *(side(r) for r in content), gap, frame]


def brand_lockup() -> Text:
    """Retro bars + white italic `DASS`, outlined black-then-white like the brand mark (6 rows, 57 cols)."""
    px = _logo_pixels()
    rows = len(px) // 2
    t = Text(no_wrap=True)
    for r in range(rows):
        t.append(" " * (rows - 1 - r))  # italic slant: one column per row
        for top, bot in zip(px[2 * r], px[2 * r + 1]):
            if top is None and bot is None:
                t.append(" ")
            elif top == bot:
                t.append("█" if top == _WHITE else "▇", style=top)
            elif bot is None:
                t.append("▀", style=top)
            elif top is None:
                t.append("▄", style=bot)
            else:
                t.append("▀", style=f"{top} on {bot}")
        t.append(" " * r)
        if r < rows - 1:
            t.append("\n")
    return t


def state_badge(state: str) -> Text:
    """Styled status pill for the top header and KPI cards."""
    styles = {
        WORKING: ("bold #0b1120 on #fbbf24", " ● WORKING "),
        CHECKING: ("bold #0b1120 on #38bdf8", " ◎ CHECKING "),
        READY: ("bold #0b1120 on #34d399", " ✓ READY "),
        NEEDS_DECISION: ("bold #0b1120 on #f87171", " ! DECISION "),
    }
    style, label = styles.get(state, ("bold #e2e8f0 on #334155", f" {state} "))
    return Text(label, style=style, no_wrap=True)


def progress_bar_text(done: int, total: int, width: int = 12) -> Text:
    """Render a crisp dual-tone progress bar that stays on one line."""
    out = Text(no_wrap=True)
    if total <= 0:
        out.append("sin fases definidas", style="#64748b")
        return out
    pct = max(0.0, min(1.0, done / total))
    filled = int(round(width * pct))
    color = "#34d399" if done == total else ("#fbbf24" if done > 0 else "#38bdf8")
    out.append("█" * filled, style=color)
    out.append("█" * (width - filled), style="#24324d")
    out.append(f" {done}/{total} ({int(pct * 100)}%)", style=f"bold {color}")
    return out


def format_kpi_plan(snap: TelemetrySnapshot, inner_width: int = 28) -> Text:
    """Build compact 4-line KPI card 1: Estado y avance del plan."""
    rep = snap.status_report
    t = Text(no_wrap=True, overflow="ellipsis")
    t.append_text(state_badge(rep.state))
    t.append("\n")
    if rep.plan:
        title = rep.plan.title
        if title.lower().startswith("plan:"):
            title = title[5:].strip()
        t.append(_clip(title, inner_width) + "\n", style="bold #f8fafc")
        bar_w = max(8, min(14, inner_width - 14))
        t.append_text(progress_bar_text(rep.plan.done, rep.plan.total, width=bar_w))
        if rep.next_task:
            t.append("\n▸ " + _clip(rep.next_task, max(10, inner_width - 2)), style="#cbd5e1")
    else:
        t.append("Sin plan activo\n", style="#94a3b8")
        t.append("aos plan new feature", style="#64748b")
    return t


def format_kpi_agents(snap: TelemetrySnapshot, inner_width: int = 28) -> Text:
    """Build compact 4-line KPI card 2: Claude Code, Antigravity & Tasks."""
    t = Text(no_wrap=True, overflow="ellipsis")
    running_sessions = [s for s in snap.sessions if s.status in ("running", "busy", "active")]
    running_tasks = [tk for tk in snap.tasks if tk.status in ("running", "in_progress")]

    claude_n = sum(1 for s in snap.sessions if s.tool == "claude-code")
    agy_n = sum(1 for s in snap.sessions if s.tool == "antigravity")
    sub_n = sum(len(s.subagents) for s in snap.sessions)

    t.append(f"{len(snap.sessions)} sesión(es)", style="bold #f8fafc")
    if running_sessions:
        t.append(f" · ● {len(running_sessions)} act.", style="bold #34d399")
    t.append("\n")
    t.append(f"Claude: {claude_n}", style="#fbbf24" if claude_n else "#64748b")
    t.append(" · ", style="#475569")
    t.append(f"Agy: {agy_n}\n", style="#38bdf8" if agy_n else "#64748b")
    t.append(f"Tasks bg: {len(snap.tasks)}", style="#e2e8f0")
    if running_tasks:
        t.append(f" ({len(running_tasks)} run)", style="bold #fbbf24")
    tok = snap.tokens
    if tok.input_tokens or tok.output_tokens:
        tok_line = f"\nTok: {format_tokens_compact(tok.input_tokens)} in · {format_tokens_compact(tok.output_tokens)} out"
        t.append(_clip(tok_line.lstrip("\n"), inner_width) if len(tok_line) - 1 > inner_width else tok_line, style="#8aa8cc")
        if not tok_line.startswith("\n"):
            pass
    else:
        t.append(f"\nSubagentes: {sub_n}", style="#94a3b8")
    return t


def format_kpi_git(snap: TelemetrySnapshot, inner_width: int = 28) -> Text:
    """Build compact 4-line KPI card 3: Workspace Git."""
    t = Text(no_wrap=True, overflow="ellipsis")
    if not snap.git.available:
        t.append("No es repositorio Git", style="#64748b")
        return t
    t.append("⎇ ", style="#34d399")
    t.append(_clip(snap.git.branch, max(10, inner_width - 2)) + "\n", style="bold #f8fafc")
    if snap.git.clean:
        t.append("✓ Árbol limpio\n", style="#34d399")
    else:
        total = len(snap.git.changes)
        untracked = sum(1 for c in snap.git.changes if "?" in c.code)
        modified = total - untracked
        t.append(f"{total} cambio(s)\n", style="bold #fbbf24")
        t.append(f"{modified} mod · {untracked} sin track\n", style="#94a3b8")
    if snap.git.recent_commits:
        t.append(_clip(snap.git.recent_commits[0], inner_width), style="#64748b")
    return t


def format_kpi_health(snap: TelemetrySnapshot, inner_width: int = 28) -> Text:
    """Build compact 4-line KPI card 4: Salud harness & conocimiento."""
    t = Text(no_wrap=True, overflow="ellipsis")
    err_n = sum(1 for f in snap.doctor_findings if f.level == "error")
    warn_n = sum(1 for f in snap.doctor_findings if f.level == "warn")
    if err_n:
        t.append(f"✖ doctor: {err_n} err", style="bold #f87171")
    else:
        t.append("✓ doctor: 0 err", style="bold #34d399")
    if warn_n:
        t.append(f" · {warn_n} warn", style="#fbbf24")
    t.append("\n")
    high_g = sum(1 for g in snap.gotchas if g["severity"] in ("critical", "high"))
    t.append(f"Gotchas: {len(snap.gotchas)}", style="#e2e8f0")
    if high_g:
        t.append(f" ({high_g} hi/crit)", style="#f87171")
    t.append(f"\nSpecs: {len(snap.specs)} · ADRs: {len(snap.adrs)}", style="#94a3b8")
    if snap.native_tools:
        up_to_date = all("día" in v.lower() for v in snap.native_tools.values())
        native_style = "#34d399" if up_to_date else "#fbbf24"
        t.append(f"\nNativos: {len(snap.native_tools)} tool(s)", style=native_style)
    return t


def format_kpi_tok_input(snap: TelemetrySnapshot, inner_width: int = 28) -> Text:
    """Token tab KPI 1: Fresh input tokens + top category."""
    tok = snap.tokens
    t = Text(no_wrap=True, overflow="ellipsis")
    t.append(format_tokens_compact(tok.input_tokens) + "\n", style="bold #8aa8cc")
    billable = tok.input_tokens + tok.output_tokens
    pct_in = int(round((tok.input_tokens / billable) * 100)) if billable else 0
    t.append(f"{pct_in}% del gasto nuevo\n", style="#cbd5e1")
    if tok.by_category:
        top = tok.by_category[0]
        t.append(_clip(f"Top: {top.name}", inner_width) + "\n", style="#fbbf24")
        t.append(_clip(f"{format_tokens_compact(top.total_tokens)} tok totales", inner_width), style="#94a3b8")
    else:
        t.append("Sin turnos registrados", style="#64748b")
    return t


def format_kpi_tok_cache(snap: TelemetrySnapshot, inner_width: int = 28) -> Text:
    """Token tab KPI 2: Prompt cache reads & cache hit ratio."""
    tok = snap.tokens
    t = Text(no_wrap=True, overflow="ellipsis")
    t.append(format_tokens_compact(tok.cache_read_tokens) + "\n", style="bold #34d399")
    denom = tok.input_tokens + tok.cache_read_tokens
    hit_pct = int(round((tok.cache_read_tokens / denom) * 100)) if denom else 0
    t.append(f"Cache hit: {hit_pct}%\n", style="bold #f8fafc")
    t.append_text(token_bar(tok.cache_read_tokens, denom, width=min(16, max(8, inner_width - 2)), color="#34d399"))
    t.append("\nPrefijo reutilizado", style="#94a3b8")
    return t


def format_kpi_tok_output(snap: TelemetrySnapshot, inner_width: int = 28) -> Text:
    """Token tab KPI 3: Generated output & thinking tokens."""
    tok = snap.tokens
    t = Text(no_wrap=True, overflow="ellipsis")
    t.append(format_tokens_compact(tok.output_tokens) + "\n", style="bold #a78bfa")
    if tok.thinking_tokens:
        think_pct = int(round((tok.thinking_tokens / tok.output_tokens) * 100)) if tok.output_tokens else 0
        t.append(f"Thinking: {format_tokens_compact(tok.thinking_tokens)} ({think_pct}%)\n", style="#cbd5e1")
    else:
        t.append("Thinking: n/d\n", style="#64748b")
    ratio = (tok.input_tokens / tok.output_tokens) if tok.output_tokens else 0.0
    t.append(f"Ratio in/out: {ratio:.1f}x\n", style="#94a3b8")
    if tok.by_tool:
        t.append(_clip(f"Top tool: {tok.by_tool[0].name}", inner_width), style="#8aa8cc")
    return t


def format_kpi_tok_context(snap: TelemetrySnapshot, inner_width: int = 28) -> Text:
    """Token tab KPI 4: Latest context window, USD cost, and always-on harness size."""
    tok = snap.tokens
    t = Text(no_wrap=True, overflow="ellipsis")
    t.append(f"Ctx: {format_tokens_compact(tok.context_window_tokens)}\n", style="bold #fbbf24")
    always_on = sum(w.est_tokens for w in tok.harness_weights if w.cost_class == "always-on")
    t.append(f"Harness fijo: ~{format_tokens_compact(always_on)}/turno\n", style="#cbd5e1")
    if tok.total_cost_usd > 0:
        t.append(f"Costo Claude: ${tok.total_cost_usd:.2f}\n", style="bold #34d399")
    else:
        t.append("Costo USD: n/d (Agy)\n", style="#64748b")
    t.append(f"Sesiones medidas: {len(tok.by_session)}", style="#94a3b8")
    return t


def format_live_event(ev: LiveEvent) -> Text:
    """Format one event row for the real-time feed."""
    level_styles = {
        "success": ("✓", "#34d399"),
        "warn": ("▲", "#fbbf24"),
        "error": ("✖", "#f87171"),
        "info": ("•", "#38bdf8"),
    }
    icon, color = level_styles.get(ev.level, ("•", "#94a3b8"))
    t = Text()
    t.append(f"{ev.timestamp} ", style="#64748b")
    t.append(f"{icon} ", style=f"bold {color}")
    t.append(f"[{ev.source}] ", style="bold #a78bfa")
    t.append(ev.message, style="#e2e8f0")
    return t


def format_diff_lines(diff_text: str) -> Iterable[Text]:
    """Colorize unified git diff lines for RichLog."""
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            yield Text(line, style="bold #94a3b8")
        elif line.startswith("@@"):
            yield Text(line, style="bold #38bdf8")
        elif line.startswith("+"):
            yield Text(line, style="#34d399")
        elif line.startswith("-"):
            yield Text(line, style="#f87171")
        elif line.startswith("diff --git") or line.startswith("index "):
            yield Text(line, style="bold #a78bfa")
        else:
            yield Text(line, style="#cbd5e1")


_OUTPUT_RULES = (
    (re.compile(r"[╭╮╰╯│]|─{2,}"), "#2f4058"),
    (re.compile(r"^\s*(▶|\$) .*"), "bold #d9b15f"),
    (re.compile(r"^(Ran \d+ tests?.*|=+ .* =+)$"), "#8aa8cc"),
    (re.compile(r"[✓√✔]|\bPASSED\b|\bpassed\b|\bOK\b|exitoso|All checks passed!?"), "bold #34d399"),
    (re.compile(r"[✗×✘]|\bFAILED\b|\bFAIL\b|\bERROR\b|\bfailed\b|Traceback.*"), "bold #c46a6a"),
    (re.compile(r"\bSKIPPED\b|\bWARN(ING)?\b"), "#d9b15f"),
)
_RULE_LINE_RE = re.compile(r"^[\s.\-=─_]+$")


def format_output_line(line: str) -> Text:
    """Terminal output line for the TUI: keep real ANSI colors, else color by meaning."""
    text = Text.from_ansi(line)
    if text.spans or not text.plain.strip():
        return text
    if _RULE_LINE_RE.match(text.plain):
        text.stylize("#2f4058")
        return text
    text.stylize("#cbd5e1")
    for pattern, style in _OUTPUT_RULES:
        text.highlight_regex(pattern, style)
    return text


_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)")


def _mark_md_line(tag: str, text: str) -> str:
    """Mark an added (+) / removed (-) markdown line without breaking table syntax."""
    if tag == " " or not text.strip() or set(text.strip()) <= set("|-: "):
        return text
    if text.lstrip().startswith("|"):
        cells = text.strip().strip("|").split("|")
        if tag == "-":
            cells = [f"~~{c.strip()}~~" if c.strip() else c for c in cells]
        cells[0] = ("**+** " if tag == "+" else "**−** ") + cells[0].strip()
        return "| " + " | ".join(c.strip() for c in cells) + " |"
    if tag == "-":
        return f"~~{text.strip()}~~"
    hashes = re.match(r"^#+\s+", text)
    if hashes:
        return hashes.group(0) + "**+** " + text[hashes.end():]
    return "**+** " + text


def markdown_diff(diff_text: str, doc_text: str) -> str:
    """Turn a unified diff of a .md file into renderable markdown.

    Each hunk keeps its context; added lines get a bold `+`, removed lines are
    struck through. A hunk that starts inside a table gets the table header
    from the current file so it still renders as a table.
    """
    doc = doc_text.splitlines()
    hunks: list = []
    for raw in diff_text.splitlines():
        m = _HUNK_RE.match(raw)
        if m:
            hunks.append((int(m.group(1)), []))
        elif hunks and raw[:1] in ("+", "-", " ") and not raw.startswith(("+++", "---")):
            hunks[-1][1].append((raw[:1], raw[1:]))
    blocks = []
    for start, lines in hunks:
        md = [_mark_md_line(tag, text) for tag, text in lines]
        if lines and lines[0][1].lstrip().startswith("|"):
            top = start - 1  # 0-based index of the hunk's first new-side line
            while top > 0 and doc[top - 1].lstrip().startswith("|"):
                top -= 1
            prefix = doc[top:start - 1] if start - 1 - top <= 2 else doc[top:top + 2]
            md = prefix + md
        blocks.append(f"*Línea {start}*\n\n" + "\n".join(md))
    return "\n\n---\n\n".join(blocks) or "*(sin cambios)*"


def format_session_age(updated_at: float) -> str:
    if not updated_at:
        return "-"
    delta = max(0, int(dt.datetime.now().timestamp() - updated_at))
    if delta < 60:
        return f"hace {delta}s"
    if delta < 3600:
        return f"hace {delta // 60}m"
    return f"hace {delta // 3600}h"


_SPARK_BLOCKS = "▁▂▃▄▅▆▇█"


def sparkline_text(samples: Sequence[int], width: int = 24) -> Text:
    """Render a compact Unicode sparkline of recent activity bursts."""
    t = Text(no_wrap=True)
    padded = ([0] * max(0, width - len(samples))) + list(samples[-width:])
    peak = max(padded) if padded else 0
    for val in padded:
        if peak <= 0 or val <= 0:
            t.append("▁", style="#111a26")  # idle baseline, barely visible
        else:
            idx = min(len(_SPARK_BLOCKS) - 1, int(round((val / peak) * (len(_SPARK_BLOCKS) - 1))))
            color = "#8aa8cc" if idx >= 5 else ("#537195" if idx >= 2 else "#2f4058")
            t.append(_SPARK_BLOCKS[idx], style=color)
    return t


def format_pulse_and_distribution(
    snap: TelemetrySnapshot,
    pulse_samples: Sequence[int],
    inner_width: int = 44,
) -> Text:
    """Gonzo-inspired telemetry summary: one labelled row per signal, label column aligned."""
    label_w = 10
    t = Text(no_wrap=True, overflow="ellipsis")

    def label(name: str) -> None:
        t.append(f"{name:<{label_w}}", style="bold #94a3b8")

    label("Actividad")
    recent_burst = pulse_samples[-1] if pulse_samples else 0
    if any(pulse_samples):
        t.append_text(sparkline_text(pulse_samples, width=min(24, max(10, inner_width - label_w - 12))))
        t.append(f"  {recent_burst} ev/tick", style="bold #d9b15f" if recent_burst else "#64748b")
    else:
        t.append("en reposo", style="#64748b")
    t.append("\n")

    # Tool distribution across detected sessions
    tool_counts: Counter = Counter()
    for sess in snap.sessions:
        for act in sess.activities:
            tool_name = act.summary.split(":", 1)[0].strip()
            if tool_name:
                tool_counts[tool_name] += 1

    top = tool_counts.most_common(3)
    if top:
        max_c = top[0][1]
        name_w = max(8, min(14, inner_width - label_w - 16))
        for i, ((name, count), color) in enumerate(zip(top, _BRAND_LIGHT)):
            label("Tools" if i == 0 else "")
            bar_len = max(1, int(round((count / max_c) * 10)))
            t.append(f"{_clip(name, name_w):<{name_w}} ", style="#e2e8f0")
            t.append("━" * bar_len, style=f"bold {color}")
            t.append("━" * (10 - bar_len), style="#1e293b")
            t.append(f" {count:>3}\n", style=f"bold {color}")
    else:
        label("Tools")
        t.append("sin actividad reciente\n", style="#64748b")

    # Open gotchas by severity; zero counts fade out
    sev_counts = Counter(g["severity"].lower() for g in snap.gotchas)
    label("Gotchas")
    for i, (key, name, color) in enumerate((
        ("critical", "crit", "#c46a6a"), ("high", "high", "#d9b15f"), ("medium", "med", "#8aa8cc"),
    )):
        n = sev_counts.get(key, 0)
        if i:
            t.append("   ")
        t.append(f"{n} {name}", style=f"bold {color}" if n else "#475569")
    t.append("\n")

    label("Gasto")
    if snap.tokens.by_category:
        top_cat = snap.tokens.by_category[0]
        total_b = snap.tokens.input_tokens + snap.tokens.output_tokens
        pct = int(round((top_cat.total_tokens / total_b) * 100)) if total_b else 0
        t.append(_clip(top_cat.name, max(8, inner_width - label_w - 6)), style="#e2e8f0")
        t.append(f"  {pct}%", style="bold #c46a6a")
    else:
        t.append("sin datos de tokens", style="#64748b")
    return t


AGENT_COLORS = {"claude-code": "#d9b15f", "antigravity": "#8aa8cc", "tui-runner": "#9aa59c"}
_AGENT_BADGES = {"claude-code": "CC", "antigravity": "AG", "tui-runner": "TUI"}
_STATUS_LOOK = {
    "running": ("▸", "bold #d9b15f"), "in_progress": ("▸", "bold #d9b15f"),
    "busy": ("▸", "bold #d9b15f"), "active": ("▸", "bold #d9b15f"),
    "recent": ("●", "#8aa8cc"), "idle": ("○", "#64748b"),
    "finished": ("✓", "#34d399"), "completed": ("✓", "#34d399"),
    "failed": ("✗", "bold #c46a6a"),
}


def agent_badge(agent: str) -> Text:
    """Short colored tag for the agent/tool that owns a session or task."""
    return Text(_AGENT_BADGES.get(agent, agent[:3].upper()), style=f"bold {AGENT_COLORS.get(agent, '#cbd5e1')}")


def status_text(status: str) -> Text:
    icon, style = _STATUS_LOOK.get(status, ("·", "#94a3b8"))
    return Text(f"{icon} {status}", style=style)


def compact_age(updated_at: float) -> str:
    return format_session_age(updated_at).replace("hace ", "")


def format_activity_row(item) -> Text:
    """Timeline row: `HH:MM  Tool  argument`, tool in gold, argument muted."""
    tool, _, arg = item.summary.partition(":")
    row = Text(no_wrap=False)
    row.append(f"{item.timestamp[:5]}  ", style="#64748b")
    row.append(tool.strip(), style="bold #d9b15f")
    if arg.strip():
        row.append(f"  {arg.strip()}", style="#cbd5e1")
    return row


def format_session_detail_summary(sess: Optional[AgentSessionInfo]) -> Text:
    t = Text()
    if sess is None:
        t.append("Selecciona una sesión para inspeccionar su actividad.", style="#64748b")
        return t
    t.append_text(agent_badge(sess.tool))
    t.append(f"  {sess.title}\n", style="bold #f8fafc")
    t.append_text(status_text(sess.status))
    t.append(f"   {sess.session_id[:8]}", style="#64748b")
    if sess.meta:
        t.append(f"   {sess.meta}", style="#8aa8cc")
    if sess.subagents:
        t.append("\nSubagentes  ", style="bold #94a3b8")
        t.append(", ".join(sess.subagents), style="#c46a6a")
    if sess.recent_tools:
        t.append("\nTools       ", style="bold #94a3b8")
        t.append(" · ".join(sess.recent_tools), style="#d9b15f")
    return t


SEVERITY_COLORS = {"critical": "#c46a6a", "high": "#c46a6a", "medium": "#d9b15f", "low": "#9aa59c"}
LEVEL_COLORS = {"error": "#c46a6a", "warn": "#d9b15f", "info": "#8aa8cc"}
KIND_COLORS = {"gotcha": "#c46a6a", "lesson": "#9aa59c", "adr": "#8aa8cc", "spec": "#d9b15f", "plan": "#d9b15f"}


def kind_text(kind: str) -> Text:
    return Text(kind.upper(), style=f"bold {KIND_COLORS.get(kind.lower(), '#cbd5e1')}")


def severity_text(sev: str) -> Text:
    return Text(sev.upper(), style=f"bold {SEVERITY_COLORS.get(sev.lower(), '#94a3b8')}")


def level_text(level: str) -> Text:
    return Text(level.upper(), style=f"bold {LEVEL_COLORS.get(level.lower(), '#94a3b8')}")


def format_knowledge_zoom(rag, findings: Sequence, gotchas: Sequence) -> Text:
    """Full-screen RAG & harness report: what the RAG retrieves, then harness health."""
    t = Text()

    def heading(title: str, hint: str = "") -> None:
        t.append(f"{title}\n", style="bold #d9b15f")
        if hint:
            t.append(f"{hint}\n", style="#64748b")
        t.append("\n")

    heading(
        "Contexto RAG (aos context)",
        "Lo que un agente recibe al empezar una tarea: fragmentos de .aos/ más parecidos a la consulta.",
    )
    if rag is None:
        t.append("  Cargando índice…\n\n", style="#64748b")
    else:
        t.append("  Modo      ", style="bold #94a3b8")
        t.append(rag.mode, style="bold #8aa8cc")
        t.append(f"   {rag.indexed_files} archivos indexados", style="#cbd5e1")
        if rag.reindexed_files:
            t.append(f" · {rag.reindexed_files} reindexados", style="#64748b")
        t.append("\n  Consulta  ", style="bold #94a3b8")
        t.append(f"{rag.query}\n" if rag.query else "(ninguna)\n", style="#e2e8f0" if rag.query else "#64748b")
        if rag.note:
            t.append(f"            {rag.note}\n", style="#64748b")
        t.append("\n")
        for i, hit in enumerate(rag.results, 1):
            t.append(f"  {i:>2}  ", style="#475569")
            t.append_text(kind_text(hit.kind))
            t.append(f"  {hit.score:.2f}  ", style="#94a3b8")
            t.append(hit.title, style="bold #f8fafc")
            if hit.section:
                t.append(f" › {hit.section}", style="#8aa8cc")
            t.append(f"\n      {hit.path}\n", style="#475569")
            snippet = " ".join(hit.snippet.split())
            if snippet:
                t.append(f"      {_clip(snippet, 160)}\n", style="#94a3b8")
            t.append("\n")
        if not rag.results:
            t.append("  Sin resultados. ", style="#64748b")
            t.append("Escribe una consulta en el buscador de la pestaña 5 para ver qué recuperaría.\n\n", style="#8aa8cc")

    heading("Auditoría del harness (aos doctor)")
    for f in findings:
        t.append("  ")
        t.append_text(level_text(f.level))
        t.append(f"  {f.area}", style="bold #e2e8f0")
        t.append(f"  {f.message}\n", style="#cbd5e1")
    if not findings:
        t.append("  OK", style="bold #34d399")
        t.append("  0 hallazgos\n", style="#cbd5e1")

    t.append("\n")
    heading("Gotchas abiertos (por gravedad)")
    for g in gotchas:
        t.append("  ")
        sev = severity_text(g["severity"])
        sev.pad_right(8 - len(sev.plain))
        t.append_text(sev)
        t.append(f"{g['date']}  ", style="#64748b")
        t.append(f"{g['title']}\n", style="#e2e8f0")
    if not gotchas:
        t.append("  Sin gotchas registrados.\n", style="#64748b")
    return t
