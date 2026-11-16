"""Read-only telemetry collector for DASS-AOS TUI and real-time monitoring.

Pure Python standard library (>=3.8) with zero external runtime dependencies.
Aggregates `.aos/` state, Git status, and local Claude Code / Antigravity
session & background task activity defensively.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from .constants import AOS_DIR_NAME, TOOL_FILES
from .doctor import CHARS_PER_TOKEN, Finding, collect_findings
from .memory import list_recent_gotchas, list_recent_lessons, missing_dependencies
from .native.manifest import native_status
from .specs import SpecInfo, open_specs, read_frontmatter
from .status import (
    StatusReport,
    active_plan_files,
    build_report,
    count_unanswered_questions,
)

_PHASE_RE = re.compile(r"^- \[([ xX])\]\s+(.+)$")
_ACTIVE_TASK_WINDOW_SECONDS = 15.0
_MAX_JSONL_TAIL_BYTES = 262_144
_MAX_TASK_TAIL_LINES = 60

_TOOL_CATEGORY_MAP = {
    "Lectura / Búsqueda": {
        "read_file", "Read", "Grep", "Glob", "list_dir", "find_by_name", "grep_search",
        "view_file", "view_file_outline", "view_code_item", "search_web", "WebFetch",
        "WebSearch", "search_code", "search_graph", "query_graph", "get_code_snippet",
        "get_file_outline", "get_architecture",
    },
    "Terminal / Comandos": {"run_command", "Bash", "PowerShell", "manage_task", "command_status"},
    "Edición / Escritura": {
        "edit_file", "write_file", "replace_file_content", "multi_replace_file_content",
        "write_to_file", "Edit", "Write", "NotebookEdit",
    },
    "Subagentes / Agentes": {
        "invoke_subagent", "define_subagent", "manage_subagents", "send_message",
        "Agent", "Task", "swarm",
    },
}

# Incremental byte-offset cache keyed by resolved JSONL path string.
_TOKEN_FILE_CACHE: Dict[str, Dict[str, Any]] = {}
# Session list shows the most recent conversations; token totals cover all of the project's.
_MAX_LISTED_SESSIONS = 15


@dataclass
class PhaseItem:
    """Single checklist phase inside a plan."""

    done: bool
    text: str
    details: List[str] = field(default_factory=list)


@dataclass
class PlanDetail:
    """Expanded view of a plan markdown file."""

    path: Path
    title: str
    status: str
    total: int
    done: int
    phases: List[PhaseItem] = field(default_factory=list)
    unanswered_questions: int = 0
    raw_markdown: str = ""


@dataclass
class GitFileChange:
    """Single entry from `git status --porcelain`."""

    code: str
    path: str


@dataclass
class GitSnapshot:
    """Summary of current Git workspace state."""

    available: bool = False
    branch: str = ""
    clean: bool = True
    changes: List[GitFileChange] = field(default_factory=list)
    diff_stat: str = ""
    recent_commits: List[str] = field(default_factory=list)


@dataclass
class AgentTaskInfo:
    """Background task or sub-task tracked by an AI tool."""

    id: str
    agent: str
    status: str
    title: str = ""
    session_id: str = ""
    log_path: Optional[Path] = None
    updated_at: float = 0.0
    tail_lines: List[str] = field(default_factory=list)


@dataclass
class AgentActivityItem:
    """Recent timeline step or tool invocation from an agent session."""

    timestamp: str
    agent: str
    kind: str
    summary: str


@dataclass
class AgentSessionInfo:
    """Active or recent session from Claude Code or Antigravity."""

    tool: str
    session_id: str
    title: str
    status: str
    cwd: str = ""
    updated_at: float = 0.0
    subagents: List[str] = field(default_factory=list)
    recent_tools: List[str] = field(default_factory=list)
    tasks: List[AgentTaskInfo] = field(default_factory=list)
    activities: List[AgentActivityItem] = field(default_factory=list)
    meta: str = ""


@dataclass
class TokenConsumer:
    """Aggregated token usage attributed to a tool or activity category."""

    name: str
    category: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class HarnessTokenWeight:
    """Estimated token footprint of `.aos/` and tool instruction files."""

    area: str
    cost_class: str
    files: int
    est_tokens: int


@dataclass
class SessionTokenSummary:
    """Cumulative token metrics for a single Claude Code or Antigravity session."""

    tool: str
    session_id: str
    title: str
    input_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    context_window_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class TokenSummary:
    """Project-wide input/cache/output token breakdown and top consumers."""

    input_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    context_window_tokens: int = 0
    total_cost_usd: float = 0.0
    by_category: List[TokenConsumer] = field(default_factory=list)
    by_tool: List[TokenConsumer] = field(default_factory=list)
    by_session: List[SessionTokenSummary] = field(default_factory=list)
    harness_weights: List[HarnessTokenWeight] = field(default_factory=list)


@dataclass
class LiveEvent:
    """Delta event emitted between two telemetry snapshots."""

    timestamp: str
    level: str  # info | success | warn | error
    source: str
    message: str


@dataclass
class TelemetrySnapshot:
    """Complete read-only snapshot of a DASS-AOS workspace."""

    timestamp: float
    project_root: Path
    status_report: StatusReport
    active_plans: List[PlanDetail] = field(default_factory=list)
    archived_plans: List[Path] = field(default_factory=list)
    specs: List[SpecInfo] = field(default_factory=list)
    adrs: List[Path] = field(default_factory=list)
    gotchas: List[Dict[str, str]] = field(default_factory=list)
    lessons: List[str] = field(default_factory=list)
    native_tools: Dict[str, str] = field(default_factory=dict)
    missing_deps: List[Tuple[str, str]] = field(default_factory=list)
    doctor_findings: List[Finding] = field(default_factory=list)
    git: GitSnapshot = field(default_factory=GitSnapshot)
    sessions: List[AgentSessionInfo] = field(default_factory=list)
    tasks: List[AgentTaskInfo] = field(default_factory=list)
    tokens: TokenSummary = field(default_factory=TokenSummary)


def _now_hms(ts: Optional[float] = None) -> str:
    stamp = ts if ts is not None else time.time()
    return dt.datetime.fromtimestamp(stamp).strftime("%H:%M:%S")


def _normalize_path_str(value: str) -> str:
    try:
        resolved = str(Path(value).resolve())
    except OSError:
        resolved = value
    return os.path.normcase(resolved.replace("\\", "/").rstrip("/"))


def _read_tail_lines(path: Path, max_bytes: int = _MAX_JSONL_TAIL_BYTES, max_lines: int = 400) -> List[str]:
    """Read the trailing lines of a text file safely without loading huge files into RAM."""
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
                raw = fh.read()
                # Drop potentially split first UTF-8/JSON line when seeking mid-file.
                nl = raw.find(b"\n")
                if nl != -1:
                    raw = raw[nl + 1:]
            else:
                raw = fh.read()
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        return lines[-max_lines:] if len(lines) > max_lines else lines
    except OSError:
        return []


def _read_head_bytes(path: Path, max_bytes: int = 65_536) -> str:
    try:
        with path.open("rb") as fh:
            return fh.read(max_bytes).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _parse_plan_detail(path: Path) -> PlanDetail:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return PlanDetail(path=path, title=path.stem, status="unknown", total=0, done=0)

    meta = read_frontmatter(path)
    title = path.stem
    phases: List[PhaseItem] = []
    done_count = 0
    current_phase: Optional[PhaseItem] = None

    for line in raw.splitlines():
        if line.startswith("# ") and title == path.stem:
            title = line[2:].strip()
            continue
        match = _PHASE_RE.match(line)
        if match:
            is_done = match.group(1).lower() == "x"
            if is_done:
                done_count += 1
            current_phase = PhaseItem(done=is_done, text=match.group(2).strip())
            phases.append(current_phase)
        elif current_phase is not None:
            stripped = line.strip()
            if stripped.startswith("- "):
                current_phase.details.append(stripped[2:].strip())
            elif stripped == "" or line.startswith("#"):
                if line.startswith("#"):
                    current_phase = None

    return PlanDetail(
        path=path,
        title=title,
        status=meta.get("status", "active"),
        total=len(phases),
        done=done_count,
        phases=phases,
        unanswered_questions=count_unanswered_questions(raw),
        raw_markdown=raw,
    )


def _list_markdown_files(directory: Path) -> List[Path]:
    if not directory.exists():
        return []
    return sorted(
        p for p in directory.glob("*.md")
        if p.name.lower() != "readme.md" and not p.name.endswith(".design.md")
    )


def _run_git(project_root: Path, args: Sequence[str]) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout
    except (OSError, subprocess.SubprocessError):
        return None


def _collect_git_snapshot(project_root: Path) -> GitSnapshot:
    inside = _run_git(project_root, ["rev-parse", "--is-inside-work-tree"])
    if not inside or inside.strip().lower() != "true":
        return GitSnapshot(available=False)

    branch = (_run_git(project_root, ["rev-parse", "--abbrev-ref", "HEAD"]) or "").strip()
    porcelain = _run_git(project_root, ["status", "--porcelain=v1", "-uall"]) or ""
    changes: List[GitFileChange] = []
    for line in porcelain.splitlines():
        if len(line) < 4:
            continue
        code = line[:2]
        path_str = line[3:].strip()
        if " -> " in path_str:
            path_str = path_str.split(" -> ", 1)[1].strip()
        changes.append(GitFileChange(code=code, path=path_str))

    diff_stat = (_run_git(project_root, ["diff", "--stat"]) or "").strip()
    log_out = _run_git(project_root, ["log", "-n", "8", "--oneline"]) or ""
    commits = [line.strip() for line in log_out.splitlines() if line.strip()]

    return GitSnapshot(
        available=True,
        branch=branch or "HEAD",
        clean=len(changes) == 0,
        changes=changes,
        diff_stat=diff_stat,
        recent_commits=commits,
    )


def read_git_file_diff(project_root: Path, rel_path: str, max_lines: int = 250) -> str:
    """Return unstaged + staged diff for a changed file, or head preview for untracked files."""
    diff_unstaged = _run_git(project_root, ["diff", "--", rel_path]) or ""
    diff_staged = _run_git(project_root, ["diff", "--cached", "--", rel_path]) or ""
    combined = "\n".join(part for part in (diff_staged.strip(), diff_unstaged.strip()) if part)
    if not combined:
        target = project_root / rel_path
        if target.is_file():
            try:
                lines = target.read_text(encoding="utf-8", errors="replace").splitlines()[:max_lines]
                return "\n".join(f"+ {line}" for line in lines) or "(archivo vacío)"
            except OSError:
                return "(no se pudo leer el archivo)"
        return "(sin diff disponible)"
    lines = combined.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... ({len(lines) - max_lines} líneas más truncadas)"]
    return "\n".join(lines)


def _encode_claude_cwd(project_root: Path) -> str:
    # Claude Code maps every non-alphanumeric char of the cwd to "-" (`_`, `.`, spaces too).
    return re.sub(r"[^A-Za-z0-9]", "-", str(project_root.resolve()))


def _find_claude_project_dir(project_root: Path, claude_home: Path) -> Optional[Path]:
    projects_dir = claude_home / "projects"
    if not projects_dir.exists():
        return None
    expected = _encode_claude_cwd(project_root).lower()
    for candidate in projects_dir.iterdir():
        if candidate.is_dir() and candidate.name.lower() == expected:
            return candidate
    return None


def _parse_claude_jsonl(
    jsonl_path: Path,
    default_title: str,
) -> Tuple[str, List[str], List[str], List[AgentActivityItem], str]:
    title = default_title
    tools: List[str] = []
    subagents: List[str] = []
    activities: List[AgentActivityItem] = []
    meta_parts: List[str] = []

    for line in _read_tail_lines(jsonl_path):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue

        ev_type = obj.get("type", "")
        ts = str(obj.get("timestamp") or "")[11:19] or "--:--:--"

        if ev_type == "ai-title" and obj.get("aiTitle"):
            title = str(obj["aiTitle"]).strip()
        elif ev_type == "tools-used" and isinstance(obj.get("tools"), list):
            for tool_name in obj["tools"]:
                if isinstance(tool_name, str) and tool_name not in tools:
                    tools.append(tool_name)
        elif ev_type == "cost-state":
            cost = obj.get("totalCostUSD")
            added = obj.get("totalLinesAdded")
            parts = []
            if isinstance(cost, (int, float)):
                parts.append(f"${cost:.2f}")
            if isinstance(added, int) and added > 0:
                parts.append(f"+{added} líneas")
            if parts:
                meta_parts = parts
        elif ev_type == "assistant":
            msg = obj.get("message") or {}
            content = msg.get("content") if isinstance(msg, dict) else None
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    tname = str(block.get("name") or "tool")
                    if tname not in tools:
                        tools.append(tname)
                    inp = block.get("input") or {}
                    detail = ""
                    if isinstance(inp, dict):
                        if tname in ("Agent", "Task"):
                            desc = str(inp.get("description") or inp.get("subagent_type") or "").strip()
                            if desc and desc not in subagents:
                                subagents.append(desc)
                            detail = desc
                        elif inp.get("file_path"):
                            detail = Path(str(inp["file_path"])).name
                        elif inp.get("command"):
                            detail = str(inp["command"])[:48]
                    summary = f"{tname}: {detail}" if detail else tname
                    activities.append(AgentActivityItem(timestamp=ts, agent="claude", kind="tool", summary=summary))

    return title, tools[-12:], subagents[-12:], activities[-20:], " · ".join(meta_parts)


def _collect_claude_tasks(session_id: str, claude_home: Path) -> List[AgentTaskInfo]:
    tasks_dir = claude_home / "tasks" / session_id
    if not tasks_dir.is_dir():
        return []
    tasks: List[AgentTaskInfo] = []
    for path in sorted(tasks_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        tid = str(data.get("id") or path.stem)
        subject = str(data.get("subject") or data.get("activeForm") or tid)
        status = str(data.get("status") or "pending")
        tasks.append(
            AgentTaskInfo(
                id=tid,
                agent="claude-code",
                status=status,
                title=subject,
                session_id=session_id,
                log_path=path,
                updated_at=path.stat().st_mtime,
                tail_lines=[f"[{status}] {subject}"],
            )
        )
    return tasks


def _parse_timestamp(raw: Any, fallback: float = 0.0) -> float:
    """Parse epoch seconds/milliseconds or ISO-8601 timestamp safely (Python 3.8+ compatible)."""
    if raw is None or raw == "":
        return fallback
    if isinstance(raw, (int, float)):
        val = float(raw)
        return val / 1000.0 if val > 1e11 else val
    text = str(raw).strip()
    try:
        val = float(text)
        return val / 1000.0 if val > 1e11 else val
    except ValueError:
        pass
    iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = dt.datetime.fromisoformat(iso_text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.timestamp()
    except ValueError:
        return fallback


def _tool_category(tool_name: str) -> str:
    for category, names in _TOOL_CATEGORY_MAP.items():
        if tool_name in names:
            return category
    return "Razonamiento / UI"


def _read_new_jsonl_lines(path: Path, kind: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Read only newly appended complete JSONL lines using a byte-offset cache."""
    key = f"{kind}:{path}"
    try:
        st = path.stat()
    except OSError:
        return {"offset": 0, "size": 0, "mtime_ns": 0, "turns": {}, "cost": 0.0, "last_ctx": 0}, []

    state = _TOKEN_FILE_CACHE.get(key)
    if state is not None:
        if st.st_size == state["size"] and st.st_mtime_ns == state["mtime_ns"]:
            return state, []
        if st.st_size < state["offset"]:
            state = None

    if state is None:
        state = {"offset": 0, "size": 0, "mtime_ns": 0, "turns": {}, "cost": 0.0, "last_ctx": 0}
        _TOKEN_FILE_CACHE[key] = state

    parsed: List[Dict[str, Any]] = []
    try:
        with path.open("rb") as fh:
            fh.seek(state["offset"])
            chunk = fh.read()
        last_nl = chunk.rfind(b"\n")
        if last_nl != -1:
            complete = chunk[: last_nl + 1]
            state["offset"] += len(complete)
            for raw_line in complete.decode("utf-8", errors="replace").splitlines():
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    obj = json.loads(raw_line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    parsed.append(obj)
        state["size"] = st.st_size
        state["mtime_ns"] = st.st_mtime_ns
    except OSError:
        pass
    return state, parsed


def _update_claude_token_file(jpath: Path) -> Dict[str, Any]:
    """Incrementally fold new lines of one Claude JSONL into its cached per-request turn map."""
    state, new_objs = _read_new_jsonl_lines(jpath, "claude")
    turns: Dict[str, Dict[str, Any]] = state["turns"]
    for idx, obj in enumerate(new_objs):
        ev_type = obj.get("type", "")
        if ev_type == "cost-state" and isinstance(obj.get("totalCostUSD"), (int, float)):
            state["cost"] = float(obj["totalCostUSD"])
            continue
        if ev_type == "ai-title" and obj.get("aiTitle"):
            state["title"] = str(obj["aiTitle"]).strip()
            continue
        if ev_type != "assistant":
            continue
        msg = obj.get("message")
        if not isinstance(msg, dict):
            continue
        usage = msg.get("usage")
        if not isinstance(usage, dict):
            continue
        # message.id + requestId identifies one API call (resumed sessions can replay it).
        call_id = obj.get("requestId") or obj.get("uuid") or "anon-{}-{}".format(state["offset"], idx)
        req_id = "{}:{}".format(msg.get("id") or "", call_id)
        entry = turns.get(req_id)
        if entry is None:
            entry = {"in": 0, "cache": 0, "out": 0, "think": 0, "tools": []}
            turns[req_id] = entry

        in_new = int(usage.get("input_tokens") or 0) + int(usage.get("cache_creation_input_tokens") or 0)
        cache_read = int(usage.get("cache_read_input_tokens") or 0)
        out_tok = int(usage.get("output_tokens") or 0)
        details = usage.get("output_tokens_details")
        think_tok = int(details.get("thinking_tokens") or 0) if isinstance(details, dict) else 0

        # Streaming chunks for the same requestId share usage; take max to avoid double counting.
        entry["in"] = max(entry["in"], in_new)
        entry["cache"] = max(entry["cache"], cache_read)
        entry["out"] = max(entry["out"], out_tok)
        entry["think"] = max(entry["think"], think_tok)
        state["last_ctx"] = max(in_new + cache_read, 0)

        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tname = str(block.get("name") or "tool")
                    entry["tools"].append(tname)
    return state


def _parse_claude_tokens(
    jpath: Path,
    session_id: str,
    title: str,
    subagent_paths: Sequence[Path] = (),
    counted: Optional[set] = None,
) -> Tuple[SessionTokenSummary, Dict[str, TokenConsumer]]:
    """Token summary of one Claude session: main transcript plus its subagent transcripts.

    ``counted`` holds API-call keys already attributed to an earlier session, so a call
    replayed by a resumed session is counted once (same rule as ccusage).
    """
    counted = set() if counted is None else counted
    main_state = _update_claude_token_file(jpath)
    turns: Dict[str, Dict[str, Any]] = {}
    for state in [main_state] + [_update_claude_token_file(p) for p in subagent_paths]:
        for key, turn in state["turns"].items():
            if key not in counted:
                counted.add(key)
                turns[key] = turn
    return _aggregate_turn_map(
        tool_name="claude-code",
        session_id=session_id,
        title=main_state.get("title") or title,
        turns=turns,
        last_ctx=main_state["last_ctx"],
        cost_usd=main_state["cost"],
    )


def _parse_antigravity_tokens(transcript: Path, session_id: str, title: str) -> Tuple[SessionTokenSummary, Dict[str, TokenConsumer]]:
    state, new_objs = _read_new_jsonl_lines(transcript, "antigravity")
    turns: Dict[str, Dict[str, Any]] = state["turns"]
    for idx, obj in enumerate(new_objs):
        if "title" not in state and obj.get("type") == "USER_INPUT" and isinstance(obj.get("content"), str):
            first = next((ln.strip() for ln in obj["content"].splitlines() if ln.strip() and not ln.strip().startswith("<")), "")
            if first:
                state["title"] = first[:44]
        in_t = obj.get("input_tokens")
        out_t = obj.get("output_tokens")
        cache_t = obj.get("cache_read_tokens")
        if in_t is None and out_t is None and cache_t is None:
            continue
        step_key = str(obj.get("step_index") if obj.get("step_index") is not None else f"step-{state['offset']}-{idx}")
        in_new = int(in_t or 0)
        cache_read = int(cache_t or 0)
        out_tok = int(out_t or 0)
        tcs = [
            str(tc.get("name") or "tool")
            for tc in (obj.get("tool_calls") or [])
            if isinstance(tc, dict) and tc.get("name")
        ]
        turns[step_key] = {
            "in": in_new,
            "cache": cache_read,
            "out": out_tok,
            "think": 0,
            "tools": tcs,
        }
        state["last_ctx"] = in_new + cache_read

    return _aggregate_turn_map(
        tool_name="antigravity",
        session_id=session_id,
        title=state.get("title") or title,
        turns=turns,
        last_ctx=state["last_ctx"],
        cost_usd=0.0,
    )


def _aggregate_turn_map(
    tool_name: str,
    session_id: str,
    title: str,
    turns: Dict[str, Dict[str, Any]],
    last_ctx: int,
    cost_usd: float,
) -> Tuple[SessionTokenSummary, Dict[str, TokenConsumer]]:
    total_in = total_cache = total_out = total_think = 0
    tool_map: Dict[str, TokenConsumer] = {}

    for turn in turns.values():
        in_t = turn["in"]
        cache_t = turn["cache"]
        out_t = turn["out"]
        think_t = turn["think"]
        total_in += in_t
        total_cache += cache_t
        total_out += out_t
        total_think += think_t

        tlist = turn["tools"]
        if not tlist:
            label = "thinking / texto" if think_t > 0 else "respuesta / texto"
            item = tool_map.setdefault(label, TokenConsumer(name=label, category="Razonamiento / UI"))
            item.calls += 1
            item.input_tokens += in_t
            item.output_tokens += out_t
            continue

        n = len(tlist)
        base_in, rem_in = divmod(in_t, n)
        base_out, rem_out = divmod(out_t, n)
        for pos, tname in enumerate(tlist):
            item = tool_map.get(tname)
            if item is None:
                item = TokenConsumer(name=tname, category=_tool_category(tname))
                tool_map[tname] = item
            item.calls += 1
            item.input_tokens += base_in + (1 if pos < rem_in else 0)
            item.output_tokens += base_out + (1 if pos < rem_out else 0)

    sess_summary = SessionTokenSummary(
        tool=tool_name,
        session_id=session_id,
        title=title,
        input_tokens=total_in,
        cache_read_tokens=total_cache,
        output_tokens=total_out,
        thinking_tokens=total_think,
        context_window_tokens=last_ctx,
        cost_usd=cost_usd,
    )
    return sess_summary, tool_map


def _estimate_dir_tokens(files: Sequence[Path]) -> Tuple[int, int]:
    count = 0
    chars = 0
    for path in files:
        if path.is_file():
            count += 1
            try:
                chars += path.stat().st_size
            except OSError:
                pass
    return count, chars // CHARS_PER_TOKEN


def _collect_harness_weights(project_root: Path) -> List[HarnessTokenWeight]:
    aos = project_root / AOS_DIR_NAME
    instr_files = [project_root / fname for fname in set(TOOL_FILES.values()) if (project_root / fname).is_file()]
    groups = [
        ("Instrucciones (CLAUDE/GEMINI/AGENTS)", "always-on", instr_files),
        ("Skills (.aos/skills/specs)", "on-demand", list((aos / "skills" / "specs").glob("*.md")) if (aos / "skills" / "specs").is_dir() else []),
        ("Roles (.aos/agents)", "delegated", list((aos / "agents").glob("*.md")) if (aos / "agents").is_dir() else []),
        ("Gotchas & Lecciones", "knowledge", (list((aos / "knowledge" / "gotchas").glob("*.md")) if (aos / "knowledge" / "gotchas").is_dir() else []) + [aos / "knowledge" / "lessons" / "LEDGER.md"]),
        ("Planes activos & Specs", "active-work", active_plan_files(project_root) + (list((aos / "specs").glob("*.md")) if (aos / "specs").is_dir() else [])),
    ]
    weights: List[HarnessTokenWeight] = []
    for area, cost_cls, paths in groups:
        n_files, est = _estimate_dir_tokens(paths)
        if n_files > 0:
            weights.append(HarnessTokenWeight(area=area, cost_class=cost_cls, files=n_files, est_tokens=est))
    weights.sort(key=lambda w: w.est_tokens, reverse=True)
    return weights


def _merge_token_summaries(
    project_root: Path,
    per_session: List[Tuple[SessionTokenSummary, Dict[str, TokenConsumer]]],
) -> TokenSummary:
    total_in = total_cache = total_out = total_think = 0
    latest_ctx = 0
    total_cost = 0.0
    by_session: List[SessionTokenSummary] = []
    merged_tools: Dict[str, TokenConsumer] = {}
    merged_cats: Dict[str, TokenConsumer] = {}

    for sess_sum, tool_map in per_session:
        if sess_sum.total_tokens + sess_sum.cache_read_tokens == 0:
            continue  # e.g. old Antigravity transcripts that predate token fields
        by_session.append(sess_sum)
        total_in += sess_sum.input_tokens
        total_cache += sess_sum.cache_read_tokens
        total_out += sess_sum.output_tokens
        total_think += sess_sum.thinking_tokens
        total_cost += sess_sum.cost_usd
        if latest_ctx == 0 and sess_sum.context_window_tokens > 0:
            latest_ctx = sess_sum.context_window_tokens

        for tname, item in tool_map.items():
            agg = merged_tools.get(tname)
            if agg is None:
                agg = TokenConsumer(name=tname, category=item.category)
                merged_tools[tname] = agg
            agg.calls += item.calls
            agg.input_tokens += item.input_tokens
            agg.output_tokens += item.output_tokens

            cat_agg = merged_cats.get(item.category)
            if cat_agg is None:
                cat_agg = TokenConsumer(name=item.category, category=item.category)
                merged_cats[item.category] = cat_agg
            cat_agg.calls += item.calls
            cat_agg.input_tokens += item.input_tokens
            cat_agg.output_tokens += item.output_tokens

    by_tool = sorted(merged_tools.values(), key=lambda c: c.total_tokens, reverse=True)
    by_category = sorted(merged_cats.values(), key=lambda c: c.total_tokens, reverse=True)
    by_session.sort(key=lambda s: s.total_tokens + s.cache_read_tokens, reverse=True)

    return TokenSummary(
        input_tokens=total_in,
        cache_read_tokens=total_cache,
        output_tokens=total_out,
        thinking_tokens=total_think,
        context_window_tokens=latest_ctx,
        total_cost_usd=total_cost,
        by_category=by_category,
        by_tool=by_tool,
        by_session=by_session,
        harness_weights=_collect_harness_weights(project_root),
    )


def _collect_claude_sessions(
    project_root: Path,
    claude_home: Path,
    token_acc: Optional[List[Tuple[SessionTokenSummary, Dict[str, TokenConsumer]]]] = None,
) -> List[AgentSessionInfo]:
    norm_root = _normalize_path_str(str(project_root))
    proj_dir = _find_claude_project_dir(project_root, claude_home)
    sessions_by_id: Dict[str, AgentSessionInfo] = {}

    sessions_dir = claude_home / "sessions"
    if sessions_dir.is_dir():
        for path in sorted(sessions_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            cwd = str(data.get("cwd") or "")
            if not cwd or _normalize_path_str(cwd) != norm_root:
                continue
            sid = str(data.get("sessionId") or path.stem)
            file_mtime = path.stat().st_mtime
            updated_raw = data.get("updatedAt") or data.get("startedAt")
            updated_ts = _parse_timestamp(updated_raw, fallback=file_mtime)
            title = str(data.get("name") or sid[:8])
            status = str(data.get("status") or "active")
            sessions_by_id[sid] = AgentSessionInfo(
                tool="claude-code",
                session_id=sid,
                title=title,
                status=status,
                cwd=cwd,
                updated_at=updated_ts,
                meta=f"pid:{data.get('pid', '?')}",
            )

    # Fallback/enrichment from ~/.claude/projects/<slug>/*.jsonl
    if proj_dir and proj_dir.is_dir():
        # Oldest first, so a replayed API call is owned by the session where it happened.
        all_jsonl = sorted(proj_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        if token_acc is not None:
            counted: set = set()
            for jpath in all_jsonl:
                subs = sorted((proj_dir / jpath.stem / "subagents").glob("*.jsonl"))
                token_acc.append(_parse_claude_tokens(jpath, jpath.stem, jpath.stem[:12], subs, counted))
        for jpath in all_jsonl[::-1][:5]:
            sid = jpath.stem
            sess = sessions_by_id.get(sid)
            if sess is None:
                sess = AgentSessionInfo(
                    tool="claude-code",
                    session_id=sid,
                    title=sid[:12],
                    status="recent",
                    cwd=str(project_root),
                    updated_at=jpath.stat().st_mtime,
                )
                sessions_by_id[sid] = sess
            title, tools, subagents, activities, meta = _parse_claude_jsonl(jpath, sess.title)
            sess.title = title
            sess.recent_tools = tools
            sess.subagents = subagents
            sess.activities = activities
            if meta:
                sess.meta = f"{sess.meta} · {meta}" if sess.meta else meta
            sess.updated_at = max(sess.updated_at, jpath.stat().st_mtime)

    for sid, sess in sessions_by_id.items():
        sess.tasks = _collect_claude_tasks(sid, claude_home)

    return sorted(sessions_by_id.values(), key=lambda s: s.updated_at, reverse=True)


def _antigravity_workspace_conversations(antigravity_home: Path, project_root: Path) -> Optional[set]:
    """Conversation ids whose workspace (per Antigravity's own index) is this project or a subfolder.

    Returns None when the index is missing/unreadable so callers can fall back to the heuristic.
    """
    db_path = antigravity_home / "conversation_summaries.db"
    if not db_path.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=1.0)
        try:
            rows = con.execute("SELECT conversation_id, workspace_uris FROM conversation_summaries").fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    root = _normalize_path_str(str(project_root))
    ids = set()
    for conv_id, uris_json in rows:
        try:
            uris = json.loads(uris_json or "[]")
        except ValueError:
            continue
        for uri in uris if isinstance(uris, list) else []:
            if not isinstance(uri, str) or not uri.startswith("file:"):
                continue
            ws = _normalize_path_str(url2pathname(unquote(urlparse(uri).path)))
            if ws == root or ws.startswith(root + "/"):
                ids.add(str(conv_id))
                break
    return ids


def _antigravity_matches_project(conv_dir: Path, project_root: Path, seen_ids: set) -> bool:
    """Heuristic fallback: the project path appears in the transcript (can misattribute)."""
    if conv_dir.name in seen_ids:
        return True
    transcript = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
    if not transcript.is_file():
        return False
    resolved = str(project_root.resolve())
    candidates = {
        resolved.lower(),
        resolved.replace("\\", "/").lower(),
        resolved.replace("\\", "\\\\").lower(),
    }
    head = _read_head_bytes(transcript, 65_536).lower()
    if any(c in head for c in candidates):
        return True
    tail_text = "\n".join(_read_tail_lines(transcript, max_bytes=65_536, max_lines=60)).lower()
    return any(c in tail_text for c in candidates)


def _summarize_agy_tool_call(tc: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    name = str(tc.get("name") or "tool")
    args = tc.get("arguments")
    if not isinstance(args, dict):
        return name, None
    if name == "invoke_subagent":
        role = str(args.get("Role") or args.get("TypeName") or "subagent").strip()
        return f"subagent: {role}", role
    for key in ("Path", "CommandLine", "toolSummary", "query"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            short = Path(val).name if key == "Path" else val.strip()[:48]
            return f"{name}: {short}", None
    return name, None


def _collect_antigravity_tasks(conv_dir: Path, now_ts: float) -> List[AgentTaskInfo]:
    tasks_dir = conv_dir / ".system_generated" / "tasks"
    if not tasks_dir.is_dir():
        return []
    tasks: List[AgentTaskInfo] = []
    for log_path in sorted(tasks_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True):
        mtime = log_path.stat().st_mtime
        tail = _read_tail_lines(log_path, max_bytes=32_768, max_lines=_MAX_TASK_TAIL_LINES)
        status = "running" if (now_ts - mtime) < _ACTIVE_TASK_WINDOW_SECONDS else "finished"
        tasks.append(
            AgentTaskInfo(
                id=log_path.stem,
                agent="antigravity",
                status=status,
                title=log_path.name,
                session_id=conv_dir.name,
                log_path=log_path,
                updated_at=mtime,
                tail_lines=tail,
            )
        )
    return tasks


def _collect_antigravity_sessions(
    project_root: Path,
    antigravity_home: Path,
    token_acc: Optional[List[Tuple[SessionTokenSummary, Dict[str, TokenConsumer]]]] = None,
) -> List[AgentSessionInfo]:
    seen_file = project_root / AOS_DIR_NAME / "native" / "antigravity-seen.txt"
    seen_ids = set(seen_file.read_text(encoding="utf-8", errors="replace").split()) if seen_file.is_file() else set()

    brain_dir = antigravity_home / "brain"
    if not brain_dir.is_dir():
        return []

    now_ts = time.time()
    workspace_ids = _antigravity_workspace_conversations(antigravity_home, project_root)
    try:
        if workspace_ids is not None:
            matched = [brain_dir / cid for cid in workspace_ids if (brain_dir / cid).is_dir()]
        else:
            recent = sorted((p for p in brain_dir.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
            matched = [p for p in recent[:_MAX_LISTED_SESSIONS] if _antigravity_matches_project(p, project_root, seen_ids)]
        matched.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []

    if token_acc is not None:
        for conv_dir in matched:
            transcript = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
            if transcript.is_file():
                token_acc.append(_parse_antigravity_tokens(transcript, conv_dir.name, conv_dir.name[:12]))

    sessions: List[AgentSessionInfo] = []
    for conv_dir in matched[:_MAX_LISTED_SESSIONS]:
        transcript = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
        tools: List[str] = []
        subagents: List[str] = []
        activities: List[AgentActivityItem] = []
        title = conv_dir.name[:12]
        last_status = "idle"
        latest_mtime = conv_dir.stat().st_mtime

        if transcript.is_file():
            latest_mtime = max(latest_mtime, transcript.stat().st_mtime)
            for line in _read_tail_lines(transcript):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(obj, dict):
                    continue
                step_type = str(obj.get("type") or "")
                step_status = str(obj.get("status") or "")
                created_at = str(obj.get("created_at") or "")
                ts_hms = created_at[11:19] if len(created_at) >= 19 else "--:--:--"

                if step_type == "USER_INPUT" and isinstance(obj.get("content"), str):
                    lines_clean = [
                        ln.strip()
                        for ln in obj["content"].splitlines()
                        if ln.strip() and not ln.strip().startswith("<")
                    ]
                    if lines_clean:
                        title = lines_clean[0][:44]

                if step_status and step_status != "DONE":
                    last_status = "running"
                elif step_status == "DONE":
                    last_status = "active" if (now_ts - latest_mtime) < 60 else "idle"

                for tc in obj.get("tool_calls") or []:
                    if not isinstance(tc, dict):
                        continue
                    tname = str(tc.get("name") or "")
                    if tname and tname not in tools:
                        tools.append(tname)
                    summary, subagent = _summarize_agy_tool_call(tc)
                    if subagent and subagent not in subagents:
                        subagents.append(subagent)
                    activities.append(
                        AgentActivityItem(timestamp=ts_hms, agent="antigravity", kind="tool", summary=summary)
                    )

        tasks = _collect_antigravity_tasks(conv_dir, now_ts)
        if any(t.status == "running" for t in tasks):
            last_status = "running"

        sessions.append(
            AgentSessionInfo(
                tool="antigravity",
                session_id=conv_dir.name,
                title=title,
                status=last_status,
                cwd=str(project_root),
                updated_at=latest_mtime,
                subagents=subagents[-12:],
                recent_tools=tools[-12:],
                tasks=tasks,
                activities=activities[-20:],
                meta=f"{len(tasks)} task(s)",
            )
        )

    return sorted(sessions, key=lambda s: s.updated_at, reverse=True)


def collect_telemetry(
    project_root: Path,
    claude_home: Optional[Path] = None,
    antigravity_home: Optional[Path] = None,
    prev_snapshot: Optional[TelemetrySnapshot] = None,
    include_slow: bool = True,
) -> TelemetrySnapshot:
    """Collect a full read-only snapshot of `.aos/`, Git, and local AI sessions.

    When ``include_slow`` is False and ``prev_snapshot`` is provided, expensive
    harness checks (`doctor`, `missing_dependencies`, `native_status`) are reused
    from ``prev_snapshot`` so high-frequency TUI polling stays lightweight.
    """
    root = project_root.resolve()
    c_home = claude_home if claude_home is not None else (Path.home() / ".claude")
    a_home = antigravity_home if antigravity_home is not None else (Path.home() / ".gemini" / "antigravity")

    active_plans = [_parse_plan_detail(p) for p in active_plan_files(root)]
    archived_plans = _list_markdown_files(root / AOS_DIR_NAME / "plans" / "archive")
    specs = open_specs(root, limit=50)
    adrs = _list_markdown_files(root / AOS_DIR_NAME / "decisions")

    gotchas = [
        {
            "title": title,
            "path": str(path),
            "filename": path.name,
            "date": date_val.isoformat(),
            "severity": severity or "medium",
        }
        for title, path, date_val, severity in list_recent_gotchas(root, limit=25)
    ]
    lessons = list_recent_lessons(root, limit=15)

    if include_slow or prev_snapshot is None:
        status_report = build_report(root)
        native_tools = native_status(root)
        missing_deps = missing_dependencies(root)
        doctor_findings = collect_findings(root)
    else:
        doctor_findings = prev_snapshot.doctor_findings
        native_tools = prev_snapshot.native_tools
        missing_deps = prev_snapshot.missing_deps
        # Recompute lightweight plan/spec status while reusing cached doctor error count.
        from .status import StatusReport, derive_state, read_plan

        plans = active_plan_files(root)
        first_plan = read_plan(plans[0]) if plans else None
        state, reason = derive_state(first_plan)
        without_pair = [s for s in specs if not s.has_counterpart]
        doc_errors = sum(1 for f in doctor_findings if f.level == "error")
        extras: List[str] = []
        if first_plan and first_plan.total:
            extras.append(f"{first_plan.done}/{first_plan.total} fases completas")
        if without_pair:
            extras.append(f"{len(without_pair)} especificación(es) sin pareja")
        extras.append(f"doctor: {doc_errors} error(es)")
        status_report = StatusReport(
            state=state,
            reason=reason,
            plan=first_plan,
            other_plans=max(len(plans) - 1, 0),
            open_specs=len(specs),
            specs_without_pair=len(without_pair),
            doctor_errors=doc_errors,
            next_task=first_plan.next_task if first_plan else None,
            extras=extras,
        )

    git_snap = _collect_git_snapshot(root)

    token_acc: List[Tuple[SessionTokenSummary, Dict[str, TokenConsumer]]] = []
    sessions = _collect_claude_sessions(root, c_home, token_acc=token_acc) + _collect_antigravity_sessions(root, a_home, token_acc=token_acc)
    sessions.sort(key=lambda s: s.updated_at, reverse=True)
    all_tasks = [task for sess in sessions for task in sess.tasks]
    all_tasks.sort(key=lambda t: t.updated_at, reverse=True)
    token_summary = _merge_token_summaries(root, token_acc)

    return TelemetrySnapshot(
        timestamp=time.time(),
        project_root=root,
        status_report=status_report,
        active_plans=active_plans,
        archived_plans=archived_plans,
        specs=specs,
        adrs=adrs,
        gotchas=gotchas,
        lessons=lessons,
        native_tools=native_tools,
        missing_deps=missing_deps,
        doctor_findings=doctor_findings,
        git=git_snap,
        sessions=sessions,
        tasks=all_tasks,
        tokens=token_summary,
    )


def diff_snapshots(prev: Optional[TelemetrySnapshot], curr: TelemetrySnapshot) -> List[LiveEvent]:
    """Produce human-readable live events describing changes between two snapshots."""
    ts = _now_hms(curr.timestamp)
    if prev is None:
        return [LiveEvent(timestamp=ts, level="info", source="tui", message=f"Monitor iniciado en {curr.project_root.name}")]

    events: List[LiveEvent] = []

    if prev.status_report.state != curr.status_report.state:
        lvl = "warn" if curr.status_report.state == "Needs decision" else "info"
        events.append(
            LiveEvent(
                timestamp=ts,
                level=lvl,
                source="status",
                message=f"Estado: {prev.status_report.state} -> {curr.status_report.state}",
            )
        )

    prev_plans = {p.path.name: p for p in prev.active_plans}
    for plan in curr.active_plans:
        old = prev_plans.get(plan.path.name)
        if old is None:
            events.append(LiveEvent(timestamp=ts, level="info", source="plan", message=f"Nuevo plan activo: {plan.path.name}"))
        elif (old.done, old.total) != (plan.done, plan.total):
            lvl = "success" if plan.done > old.done else "info"
            events.append(
                LiveEvent(
                    timestamp=ts,
                    level=lvl,
                    source="plan",
                    message=f"{plan.path.name}: {plan.done}/{plan.total} fases",
                )
            )

    prev_git = {c.path: c.code for c in prev.git.changes}
    curr_git = {c.path: c.code for c in curr.git.changes}
    for path, code in curr_git.items():
        if path not in prev_git:
            events.append(LiveEvent(timestamp=ts, level="info", source="git", message=f"Archivo tocado ({code.strip() or '?'}): {path}"))
        elif prev_git[path] != code:
            events.append(LiveEvent(timestamp=ts, level="info", source="git", message=f"Git {path}: {prev_git[path].strip()} -> {code.strip()}"))

    prev_tasks = {(t.agent, t.session_id, t.id): t for t in prev.tasks}
    for task in curr.tasks:
        key = (task.agent, task.session_id, task.id)
        old_task = prev_tasks.get(key)
        if old_task is None:
            events.append(LiveEvent(timestamp=ts, level="info", source=task.agent, message=f"Nueva task {task.id} ({task.status})"))
        elif old_task.status != task.status:
            lvl = "success" if task.status in ("finished", "completed") else "info"
            events.append(LiveEvent(timestamp=ts, level=lvl, source=task.agent, message=f"Task {task.id}: {old_task.status} -> {task.status}"))

    prev_sessions = {(s.tool, s.session_id): s for s in prev.sessions}
    for sess in curr.sessions:
        skey = (sess.tool, sess.session_id)
        old_s = prev_sessions.get(skey)
        if old_s is None:
            events.append(LiveEvent(timestamp=ts, level="info", source=sess.tool, message=f"Sesión detectada: {sess.title}"))
        elif len(sess.activities) > len(old_s.activities) and sess.activities:
            latest = sess.activities[-1]
            events.append(LiveEvent(timestamp=ts, level="info", source=sess.tool, message=latest.summary))

    return events
