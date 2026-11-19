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
# Incremental file stat cache keyed by `<namespace>:<path>` -> (mtime_ns, size, cached_value).
_STAT_CACHE: Dict[str, Tuple[int, int, Any]] = {}
# Session list shows the most recent conversations; token totals cover all of the project's.
_MAX_LISTED_SESSIONS = 15


def _cached_by_stat(namespace: str, path: Path, builder: Any) -> Any:
    """Return cached result when `(st_mtime_ns, st_size)` has not changed (`CA-1`)."""
    key = f"{namespace}:{path}"
    try:
        st = path.stat()
    except OSError:
        return builder()
    entry = _STAT_CACHE.get(key)
    if entry is not None and entry[0] == st.st_mtime_ns and entry[1] == st.st_size:
        return entry[2]
    val = builder()
    _STAT_CACHE[key] = (st.st_mtime_ns, st.st_size, val)
    return val


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
    """Background task, subagent, workflow, or scheduled job tracked by an AI tool."""

    id: str
    agent: str
    status: str
    title: str = ""
    session_id: str = ""
    log_path: Optional[Path] = None
    started_at: float = 0.0
    updated_at: float = 0.0
    tail_lines: List[str] = field(default_factory=list)
    kind: str = "task"  # task | subagent | workflow | cron
    agent_type: str = ""

    def __post_init__(self) -> None:
        if self.started_at <= 0.0 and self.updated_at > 0.0:
            self.started_at = self.updated_at
        elif self.updated_at <= 0.0 and self.started_at > 0.0:
            self.updated_at = self.started_at

    @property
    def duration_seconds(self) -> float:
        if self.started_at <= 0.0:
            return 0.0
        end = self.updated_at if self.updated_at >= self.started_at else time.time()
        return max(0.0, end - self.started_at)


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
    pending_reason: str = ""
    workflows: List[str] = field(default_factory=list)
    touched_files: List[str] = field(default_factory=list)
    voice_active: bool = False
    last_assistant_text: str = ""
    summary_title: str = ""


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
    cost_estimated: bool = False

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
    cost_estimated: bool = False
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


_VOICE_TOGGLE_RE = re.compile(r"Turned (on|off) voice mode", re.IGNORECASE)


def _voice_state_from_text(text: str, current: bool) -> bool:
    """Last `/voice` stdout wins: Claude Code logs `Turned on/off voice mode`."""
    hits = _VOICE_TOGGLE_RE.findall(text)
    return hits[-1].lower() == "on" if hits else current


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
    def _build() -> PlanDetail:
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

    return _cached_by_stat("plan", path, _build)


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


_GIT_LOG_CACHE: Dict[Tuple[str, str], List[str]] = {}
_DEPS_CACHE: Dict[str, Tuple[float, List[Tuple[str, str]]]] = {}
_DEPS_CACHE_TTL_SECONDS = 45.0


def _read_git_head_sha(project_root: Path) -> str:
    """Resolve current Git HEAD commit SHA directly from `.git/` in <0.1ms (no subprocess)."""
    git_entry = project_root / ".git"
    try:
        if git_entry.is_file():
            raw = git_entry.read_text(encoding="utf-8", errors="ignore").strip()
            if raw.startswith("gitdir:"):
                git_dir = Path(raw.split(":", 1)[1].strip())
                if not git_dir.is_absolute():
                    git_dir = (project_root / git_dir).resolve()
            else:
                return ""
        elif git_entry.is_dir():
            git_dir = git_entry
        else:
            return ""

        head_file = git_dir / "HEAD"
        if not head_file.is_file():
            return ""
        head_txt = head_file.read_text(encoding="utf-8", errors="ignore").strip()
        if not head_txt.startswith("ref:"):
            return head_txt
        ref_rel = head_txt.split(":", 1)[1].strip()
        ref_file = git_dir / ref_rel
        if ref_file.is_file():
            return ref_file.read_text(encoding="utf-8", errors="ignore").strip()
        # Fallback for packed refs
        packed = git_dir / "packed-refs"
        if packed.is_file():
            for line in packed.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("#") or " " not in line:
                    continue
                sha, ref_name = line.split(" ", 1)
                if ref_name.strip() == ref_rel:
                    return sha.strip()
        return head_txt
    except OSError:
        return ""


def _parse_porcelain_branch(header_line: str) -> str:
    """Extract branch name from `git status --porcelain=v1 -b` header (`## ...`)."""
    raw = header_line[2:].strip()
    if raw.startswith("No commits yet on "):
        return raw[len("No commits yet on "):].strip() or "HEAD"
    if raw.startswith("Initial commit on "):
        return raw[len("Initial commit on "):].strip() or "HEAD"
    if raw.startswith("HEAD ("):
        return "HEAD"
    if "..." in raw:
        raw = raw.split("...", 1)[0].strip()
    return raw or "HEAD"


def _collect_git_snapshot(project_root: Path) -> GitSnapshot:
    porcelain = _run_git(project_root, ["status", "--porcelain=v1", "-b", "-uall"])
    if porcelain is None:
        return GitSnapshot(available=False)

    branch = "HEAD"
    changes: List[GitFileChange] = []
    for line in porcelain.splitlines():
        if line.startswith("##"):
            branch = _parse_porcelain_branch(line)
            continue
        if len(line) < 4:
            continue
        code = line[:2]
        path_str = line[3:].strip()
        if " -> " in path_str:
            path_str = path_str.split(" -> ", 1)[1].strip()
        changes.append(GitFileChange(code=code, path=path_str))

    head_sha = _read_git_head_sha(project_root)
    cache_key = (str(project_root), head_sha)
    if head_sha and cache_key in _GIT_LOG_CACHE:
        commits = _GIT_LOG_CACHE[cache_key]
    else:
        log_out = _run_git(project_root, ["log", "-n", "8", "--oneline"]) or ""
        commits = [line.strip() for line in log_out.splitlines() if line.strip()]
        if head_sha:
            if len(_GIT_LOG_CACHE) > 32:
                _GIT_LOG_CACHE.clear()
            _GIT_LOG_CACHE[cache_key] = commits

    return GitSnapshot(
        available=True,
        branch=branch,
        clean=len(changes) == 0,
        changes=changes,
        diff_stat="",
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


def _relativize_project_path(raw_path: str, project_root: Path) -> str:
    text = str(raw_path or "").strip()
    if not text:
        return ""
    try:
        resolved = Path(text).resolve()
        root_res = project_root.resolve()
        rel = resolved.relative_to(root_res)
        return str(rel).replace("\\", "/")
    except (OSError, ValueError):
        return text.replace("\\", "/")


def _extract_first_question(questions_obj: Any) -> str:
    if isinstance(questions_obj, list):
        for q in questions_obj:
            if isinstance(q, dict) and q.get("question"):
                return str(q["question"]).strip()
    return ""


def _parse_claude_jsonl(
    jsonl_path: Path,
    default_title: str,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    def _build() -> Dict[str, Any]:
        title = default_title
        tools: List[str] = []
        subagents: List[str] = []
        workflows: List[str] = []
        touched_files: List[str] = []
        inline_tasks: List[AgentTaskInfo] = []
        activities: List[AgentActivityItem] = []
        meta_parts: List[str] = []
        pending_tools: Dict[str, Tuple[str, str]] = {}
        voice_active = False
        last_assistant_text = ""

        try:
            fallback_ts = jsonl_path.stat().st_mtime
        except OSError:
            fallback_ts = time.time()

        sid = jsonl_path.stem
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
            raw_ts = obj.get("timestamp")
            ev_ts = _parse_timestamp(raw_ts, fallback=fallback_ts)
            ts = str(raw_ts or "")[11:19] or "--:--:--"

            if ev_type == "ai-title" and obj.get("aiTitle"):
                title = str(obj["aiTitle"]).strip()
            elif ev_type == "custom-title" and obj.get("customTitle"):
                title = str(obj["customTitle"]).strip()
            elif ev_type == "mode":
                mode_val = str(obj.get("mode") or "").lower()
                if "voice" in mode_val:
                    voice_active = True
            elif ev_type == "system" and obj.get("subtype") == "local_command":
                voice_active = _voice_state_from_text(str(obj.get("content") or ""), voice_active)
            elif ev_type == "file-history-delta":
                tpath = str(obj.get("trackingPath") or "").strip()
                if tpath:
                    rel = _relativize_project_path(tpath, project_root) if project_root else tpath
                    if rel and rel not in touched_files:
                        touched_files.append(rel)
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
            elif ev_type == "user":
                msg = obj.get("message") or {}
                content = msg.get("content") if isinstance(msg, dict) else None
                if isinstance(content, str):
                    voice_active = _voice_state_from_text(content, voice_active)
                    pending_tools.clear()
                elif isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        if btype == "tool_result":
                            tuid = str(block.get("tool_use_id") or "")
                            pending_tools.pop(tuid, None)
                        elif btype == "text":
                            txt = str(block.get("text") or "")
                            voice_active = _voice_state_from_text(txt, voice_active)
                            pending_tools.clear()
            elif ev_type == "assistant":
                msg = obj.get("message") or {}
                content = msg.get("content") if isinstance(msg, dict) else None
                stop_reason = str(msg.get("stop_reason") or "") if isinstance(msg, dict) else ""
                if stop_reason and stop_reason != "tool_use":
                    pending_tools.clear()
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        if btype == "text" and block.get("text"):
                            txt_val = str(block["text"]).strip()
                            if txt_val:
                                last_assistant_text = txt_val
                            continue
                        if btype != "tool_use":
                            continue
                        tname = str(block.get("name") or "tool")
                        tuid = str(block.get("id") or f"tu-{len(activities)}")
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
                                if inp.get("run_in_background"):
                                    inline_tasks.append(
                                        AgentTaskInfo(
                                            id=tuid,
                                            agent="claude-code",
                                            status="running",
                                            title=desc or tname,
                                            session_id=sid,
                                            log_path=jsonl_path,
                                            started_at=ev_ts,
                                            updated_at=ev_ts,
                                            tail_lines=[f"[{tname}] {desc}"],
                                            kind="subagent",
                                            agent_type=str(inp.get("subagent_type") or "agent"),
                                        )
                                    )
                            elif tname == "Workflow":
                                spath = str(inp.get("scriptPath") or inp.get("workflow") or "").strip()
                                wname = Path(spath).name if spath else "workflow"
                                wlabel = f"Workflow: {wname}"
                                if wlabel not in workflows:
                                    workflows.append(wlabel)
                                detail = wname
                                inline_tasks.append(
                                    AgentTaskInfo(
                                        id=tuid,
                                        agent="claude-code",
                                        status="finished",
                                        title=wlabel,
                                        session_id=sid,
                                        log_path=jsonl_path,
                                        started_at=ev_ts,
                                        updated_at=ev_ts,
                                        tail_lines=[f"Workflow {spath}"],
                                        kind="workflow",
                                    )
                                )
                            elif tname == "Skill":
                                sk_name = str(inp.get("skill") or "").strip()
                                if sk_name:
                                    slabel = f"Skill: {sk_name}"
                                    if slabel not in workflows:
                                        workflows.append(slabel)
                                    detail = sk_name
                            elif tname in ("EnterPlanMode", "ExitPlanMode"):
                                plabel = f"PlanMode ({tname})"
                                if plabel not in workflows:
                                    workflows.append(plabel)
                                detail = tname
                            elif tname == "SendMessage":
                                to_target = str(inp.get("to") or inp.get("recipient") or "agent").strip()
                                msg_preview = str(inp.get("summary") or inp.get("message") or "").strip()[:48]
                                detail = f"-> {to_target}: {msg_preview}".rstrip(": ")
                            elif tname == "CronCreate":
                                cron_expr = str(inp.get("cron") or "").strip()
                                cron_prompt = str(inp.get("prompt") or "").strip()[:40]
                                detail = f"{cron_expr} {cron_prompt}".strip()
                                inline_tasks.append(
                                    AgentTaskInfo(
                                        id=tuid,
                                        agent="claude-code",
                                        status="running",
                                        title=f"cron: {detail}",
                                        session_id=sid,
                                        log_path=jsonl_path,
                                        started_at=ev_ts,
                                        updated_at=ev_ts,
                                        tail_lines=[f"[cron {cron_expr}] {cron_prompt}"],
                                        kind="cron",
                                    )
                                )
                            elif inp.get("file_path") or inp.get("notebook_path"):
                                raw_fp = str(inp.get("file_path") or inp.get("notebook_path"))
                                detail = Path(raw_fp).name
                                if tname in ("Write", "Edit", "NotebookEdit"):
                                    rel = _relativize_project_path(raw_fp, project_root) if project_root else raw_fp
                                    if rel and rel not in touched_files:
                                        touched_files.append(rel)
                            elif inp.get("command"):
                                cmd_str = str(inp["command"])
                                detail = cmd_str[:48]
                                if inp.get("run_in_background"):
                                    inline_tasks.append(
                                        AgentTaskInfo(
                                            id=tuid,
                                            agent="claude-code",
                                            status="running",
                                            title=f"{tname}: {detail}",
                                            session_id=sid,
                                            log_path=jsonl_path,
                                            started_at=ev_ts,
                                            updated_at=ev_ts,
                                            tail_lines=[f"$ {cmd_str}"],
                                            kind="task",
                                        )
                                    )

                            # Track pending reason until tool_result arrives
                            if tname == "AskUserQuestion":
                                q_txt = _extract_first_question(inp.get("questions"))
                                pending_tools[tuid] = (tname, f"Pregunta: {q_txt}" if q_txt else "Pregunta al usuario")
                            elif tname == "ExitPlanMode":
                                pending_tools[tuid] = (tname, "Aprobación de plan (ExitPlanMode)")
                            elif stop_reason == "tool_use":
                                pending_tools[tuid] = (
                                    tname,
                                    f"Permiso/ejecución pendiente: {tname}" + (f" ({detail})" if detail else ""),
                                )

                        summary = f"{tname}: {detail}" if detail else tname
                        activities.append(AgentActivityItem(timestamp=ts, agent="claude", kind="tool", summary=summary))

        # Mark inline tasks finished if their tool_result arrived
        for tk in inline_tasks:
            if tk.id not in pending_tools and tk.kind in ("task", "subagent"):
                tk.status = "finished"

        pending_reason = ""
        if pending_tools:
            _, pending_reason = list(pending_tools.values())[-1]

        return {
            "title": title,
            "tools": tools[-12:],
            "subagents": subagents[-12:],
            "workflows": workflows[-12:],
            "touched_files": touched_files[-25:],
            "inline_tasks": inline_tasks[-15:],
            "activities": activities[-20:],
            "meta": " · ".join(meta_parts),
            "pending_reason": pending_reason,
            "voice_active": voice_active,
            "last_assistant_text": last_assistant_text,
        }

    return _cached_by_stat("claude_jsonl", jsonl_path, _build)


def _parse_claude_subagent_pair(meta_path: Optional[Path], jsonl_path: Optional[Path], session_id: str) -> Optional[AgentTaskInfo]:
    anchor = jsonl_path or meta_path
    if anchor is None:
        return None

    def _build() -> Optional[AgentTaskInfo]:
        meta: Dict[str, Any] = {}
        if meta_path and meta_path.is_file():
            try:
                loaded = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
                if isinstance(loaded, dict):
                    meta = loaded
            except (OSError, ValueError):
                pass

        stem = anchor.stem.replace(".meta", "")
        agent_type = str(meta.get("agentType") or "subagent").strip()
        desc = str(meta.get("description") or stem).strip()
        finished = bool(meta.get("finished"))

        try:
            st = anchor.stat()
            started_at = min(st.st_ctime, st.st_mtime)
            updated_at = st.st_mtime
        except OSError:
            started_at = updated_at = time.time()

        tail_lines: List[str] = [f"[{agent_type}] {desc}"]
        if jsonl_path and jsonl_path.is_file():
            try:
                jst = jsonl_path.stat()
                updated_at = max(updated_at, jst.st_mtime)
            except OSError:
                pass
            head_chunk = _read_head_bytes(jsonl_path, 4096)
            first_line = next((ln.strip() for ln in head_chunk.splitlines() if ln.strip()), "")
            if first_line:
                try:
                    fobj = json.loads(first_line)
                    if isinstance(fobj, dict) and fobj.get("timestamp"):
                        started_at = _parse_timestamp(fobj.get("timestamp"), fallback=started_at)
                except ValueError:
                    pass
            raw_tail = _read_tail_lines(jsonl_path, max_bytes=32_768, max_lines=30)
            for rln in raw_tail[-12:]:
                try:
                    robj = json.loads(rln)
                except ValueError:
                    continue
                if not isinstance(robj, dict):
                    continue
                if robj.get("timestamp"):
                    updated_at = _parse_timestamp(robj.get("timestamp"), fallback=updated_at)
                msg = robj.get("message") or {}
                content = msg.get("content") if isinstance(msg, dict) else None
                if isinstance(content, list):
                    for blk in content:
                        if isinstance(blk, dict):
                            if blk.get("type") == "tool_use":
                                tail_lines.append(f"▸ {blk.get('name', 'tool')}")
                            elif blk.get("type") == "text" and blk.get("text"):
                                tail_lines.append(str(blk["text"]).strip()[:120])

        status = "finished" if finished else "running"
        return AgentTaskInfo(
            id=stem,
            agent="claude-code",
            status=status,
            title=f"{agent_type}: {desc}" if desc != stem else stem,
            session_id=session_id,
            log_path=jsonl_path or meta_path,
            started_at=started_at,
            updated_at=max(started_at, updated_at),
            tail_lines=tail_lines[-_MAX_TASK_TAIL_LINES:],
            kind="subagent",
            agent_type=agent_type,
        )

    key = f"claude_subagent:{meta_path}:{jsonl_path}"
    sig_mtime = 0
    sig_size = 0
    for p in (meta_path, jsonl_path):
        if p is not None:
            try:
                pst = p.stat()
                sig_mtime ^= pst.st_mtime_ns
                sig_size += pst.st_size
            except OSError:
                pass
    entry = _STAT_CACHE.get(key)
    if entry is not None and entry[0] == sig_mtime and entry[1] == sig_size:
        return entry[2]
    val = _build()
    _STAT_CACHE[key] = (sig_mtime, sig_size, val)
    return val


def _collect_claude_tasks(
    session_id: str,
    claude_home: Path,
    proj_dir: Optional[Path] = None,
    inline_tasks: Sequence[AgentTaskInfo] = (),
) -> List[AgentTaskInfo]:
    tasks: List[AgentTaskInfo] = list(inline_tasks)
    tasks_dir = claude_home / "tasks" / session_id
    if tasks_dir.is_dir():
        for path in sorted(tasks_dir.glob("*.json")):
            try:
                st = path.stat()
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            tid = str(data.get("id") or path.stem)
            subject = str(data.get("subject") or data.get("activeForm") or tid)
            status = str(data.get("status") or "pending")
            started_at = _parse_timestamp(
                data.get("createdAt") or data.get("startedAt"),
                fallback=min(st.st_ctime, st.st_mtime),
            )
            updated_at = _parse_timestamp(data.get("updatedAt"), fallback=st.st_mtime)
            tasks.append(
                AgentTaskInfo(
                    id=tid,
                    agent="claude-code",
                    status=status,
                    title=subject,
                    session_id=session_id,
                    log_path=path,
                    started_at=started_at,
                    updated_at=max(started_at, updated_at),
                    tail_lines=[f"[{status}] {subject}"],
                    kind="task",
                )
            )

    if proj_dir is not None:
        sess_dir = proj_dir / session_id
        sub_dir = sess_dir / "subagents"
        if sub_dir.is_dir():
            stems = sorted({
                p.name.replace(".meta.json", "").replace(".jsonl", "")
                for p in sub_dir.iterdir()
                if p.name.endswith(".meta.json") or p.name.endswith(".jsonl")
            })
            for stem in stems:
                meta_p = sub_dir / f"{stem}.meta.json"
                jsonl_p = sub_dir / f"{stem}.jsonl"
                sub_info = _parse_claude_subagent_pair(
                    meta_p if meta_p.is_file() else None,
                    jsonl_p if jsonl_p.is_file() else None,
                    session_id,
                )
                if sub_info is not None:
                    tasks.append(sub_info)

        tr_dir = sess_dir / "tool-results"
        if tr_dir.is_dir():
            for txt_path in sorted(tr_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
                try:
                    st = txt_path.stat()
                except OSError:
                    continue
                tail = _cached_by_stat(
                    "claude_tr",
                    txt_path,
                    lambda p=txt_path: _read_tail_lines(p, max_bytes=16_384, max_lines=_MAX_TASK_TAIL_LINES),
                )
                tasks.append(
                    AgentTaskInfo(
                        id=txt_path.stem,
                        agent="claude-code",
                        status="finished",
                        title=f"output: {txt_path.stem}",
                        session_id=session_id,
                        log_path=txt_path,
                        started_at=min(st.st_ctime, st.st_mtime),
                        updated_at=st.st_mtime,
                        tail_lines=tail,
                        kind="task",
                    )
                )

    tasks.sort(key=lambda t: t.updated_at, reverse=True)
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


def _update_claude_token_file(jpath: Path, project_root: Optional[Path] = None) -> Dict[str, Any]:
    """Incrementally fold new lines of one Claude JSONL into its cached per-request turn map."""
    state, new_objs = _read_new_jsonl_lines(jpath, "claude")
    turns: Dict[str, Dict[str, Any]] = state["turns"]
    subagents: List[str] = state.setdefault("subagents", [])
    workflows: List[str] = state.setdefault("workflows", [])
    touched_files: List[str] = state.setdefault("touched_files", [])
    for idx, obj in enumerate(new_objs):
        ev_type = obj.get("type", "")
        if ev_type == "cost-state" and isinstance(obj.get("totalCostUSD"), (int, float)):
            state["cost"] = float(obj["totalCostUSD"])
            continue
        if ev_type == "ai-title" and obj.get("aiTitle"):
            state["title"] = str(obj["aiTitle"]).strip()
            continue
        if ev_type == "file-history-delta":
            tpath = str(obj.get("trackingPath") or "").strip()
            if tpath:
                rel = _relativize_project_path(tpath, project_root) if project_root else tpath
                if rel and rel not in touched_files:
                    touched_files.append(rel)
            continue
        if ev_type != "assistant":
            continue
        msg = obj.get("message")
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                tname = str(block.get("name") or "tool")
                inp = block.get("input") if isinstance(block.get("input"), dict) else {}
                if tname in ("Agent", "Task"):
                    desc = str(inp.get("description") or inp.get("subagent_type") or "").strip()
                    if desc and desc not in subagents:
                        subagents.append(desc)
                elif tname == "Workflow":
                    spath = str(inp.get("scriptPath") or inp.get("workflow") or "").strip()
                    wlabel = f"Workflow: {Path(spath).name if spath else 'workflow'}"
                    if wlabel not in workflows:
                        workflows.append(wlabel)
                elif tname == "Skill" and inp.get("skill"):
                    slabel = f"Skill: {inp['skill']}"
                    if slabel not in workflows:
                        workflows.append(slabel)
                elif tname in ("EnterPlanMode", "ExitPlanMode"):
                    plabel = f"PlanMode ({tname})"
                    if plabel not in workflows:
                        workflows.append(plabel)
                elif tname in ("Write", "Edit", "NotebookEdit"):
                    raw_fp = str(inp.get("file_path") or inp.get("notebook_path") or "").strip()
                    if raw_fp:
                        rel = _relativize_project_path(raw_fp, project_root) if project_root else raw_fp
                        if rel and rel not in touched_files:
                            touched_files.append(rel)

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
    project_root: Optional[Path] = None,
) -> Tuple[SessionTokenSummary, Dict[str, TokenConsumer]]:
    """Token summary of one Claude session: main transcript plus its subagent transcripts.

    ``counted`` holds API-call keys already attributed to an earlier session, so a call
    replayed by a resumed session is counted once (same rule as ccusage).
    """
    counted = set() if counted is None else counted
    main_state = _update_claude_token_file(jpath, project_root=project_root)
    turns: Dict[str, Dict[str, Any]] = {}
    for state in [main_state] + [_update_claude_token_file(p, project_root=project_root) for p in subagent_paths]:
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


def _estimate_turn_cost_usd(model: str, in_new: int, cache_read: int, out_tok: int) -> float:
    """Estimate API-equivalent USD cost for one turn from `(model, input, cache_read, output)`."""
    m = (model or "").lower()
    ctx = in_new + cache_read
    if "opus" in m:
        in_r, cache_r, out_r = 15.0, 1.50, 75.0
    elif "sonnet" in m:
        in_r, cache_r, out_r = 3.0, 0.30, 15.0
    elif "haiku" in m:
        in_r, cache_r, out_r = 0.80, 0.08, 4.0
    elif "flash-lite" in m or "flash_lite" in m:
        in_r, cache_r, out_r = 0.10, 0.025, 0.40
    elif "flash" in m:
        in_r, cache_r, out_r = 0.30, 0.075, 2.50
    elif ctx > 200_000:
        in_r, cache_r, out_r = 2.50, 0.625, 15.0
    else:
        in_r, cache_r, out_r = 1.25, 0.31, 10.0
    return (in_new * in_r + cache_read * cache_r + out_tok * out_r) / 1_000_000.0


def _parse_antigravity_tokens(transcript: Path, session_id: str, title: str) -> Tuple[SessionTokenSummary, Dict[str, TokenConsumer]]:
    state, new_objs = _read_new_jsonl_lines(transcript, "antigravity")
    turns: Dict[str, Dict[str, Any]] = state["turns"]
    subagents: List[str] = state.setdefault("subagents", [])
    workflows: List[str] = state.setdefault("workflows", [])
    for idx, obj in enumerate(new_objs):
        if "title" not in state and obj.get("type") == "USER_INPUT" and isinstance(obj.get("content"), str):
            first = next((ln.strip() for ln in obj["content"].splitlines() if ln.strip() and not ln.strip().startswith("<")), "")
            if first:
                state["title"] = first[:44]
        elif "title" not in state and obj.get("type") == "SYSTEM_MESSAGE" and isinstance(obj.get("content"), str):
            m_sys = _AGY_SYS_MSG_RE.search(obj["content"])
            if m_sys and "/" not in m_sys.group(1):
                body_first = next((ln.strip() for ln in m_sys.group(2).splitlines() if ln.strip() and not ln.strip().startswith("<")), "")
                if body_first:
                    state["title"] = f"↳ {body_first[:40]}"
        for tc in (obj.get("tool_calls") or []):
            if not isinstance(tc, dict):
                continue
            _, sub = _summarize_agy_tool_call(tc)
            if sub and sub not in subagents:
                subagents.append(sub)
            if tc.get("name") == "run_workflow":
                wargs = _extract_agy_tc_args(tc)
                wdesc = str(wargs.get("Description") or wargs.get("ScriptPath") or "workflow").strip()
                wlbl = f"run_workflow: {wdesc}"
                if wlbl not in workflows:
                    workflows.append(wlbl)
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
        model_name = str(obj.get("model") or "")
        turns[step_key] = {
            "in": in_new,
            "cache": cache_read,
            "out": out_tok,
            "think": 0,
            "tools": tcs,
            "cost": _estimate_turn_cost_usd(model_name, in_new, cache_read, out_tok),
        }
        state["last_ctx"] = in_new + cache_read

    est_cost = sum(float(t.get("cost") or 0.0) for t in turns.values())
    return _aggregate_turn_map(
        tool_name="antigravity",
        session_id=session_id,
        title=state.get("title") or title,
        turns=turns,
        last_ctx=state["last_ctx"],
        cost_usd=est_cost,
        cost_estimated=est_cost > 0.0,
    )


def _aggregate_turn_map(
    tool_name: str,
    session_id: str,
    title: str,
    turns: Dict[str, Dict[str, Any]],
    last_ctx: int,
    cost_usd: float,
    cost_estimated: bool = False,
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
        cost_estimated=cost_estimated,
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
        cost_estimated=any(s.cost_estimated for s in by_session),
        by_category=by_category,
        by_tool=by_tool,
        by_session=by_session,
        harness_weights=_collect_harness_weights(project_root),
    )


def _collect_claude_team_members(claude_home: Path) -> Dict[str, List[str]]:
    teams_dir = claude_home / "teams"
    if not teams_dir.is_dir():
        return {}
    by_session: Dict[str, List[str]] = {}
    for cfg in sorted(teams_dir.glob("*/config.json")):
        try:
            data = json.loads(cfg.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        lead_sid = str(data.get("leadSessionId") or "").strip()
        if not lead_sid and cfg.parent.name.startswith("session-"):
            lead_sid = cfg.parent.name[len("session-"):]
        if not lead_sid:
            continue
        members: List[str] = []
        for m in data.get("members") or []:
            if isinstance(m, dict) and m.get("name"):
                mname = str(m["name"]).strip()
                mtype = str(m.get("agentType") or "").strip()
                label = f"{mname} ({mtype})" if mtype and mtype != mname else mname
                if label not in members:
                    members.append(label)
        if members:
            by_session.setdefault(lead_sid, []).extend(members)
    return by_session


def _collect_claude_sessions(
    project_root: Path,
    claude_home: Path,
    token_acc: Optional[List[Tuple[SessionTokenSummary, Dict[str, TokenConsumer]]]] = None,
) -> List[AgentSessionInfo]:
    norm_root = _normalize_path_str(str(project_root))
    proj_dir = _find_claude_project_dir(project_root, claude_home)
    sessions_by_id: Dict[str, AgentSessionInfo] = {}
    team_members = _collect_claude_team_members(claude_home)

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

    inline_by_sid: Dict[str, List[AgentTaskInfo]] = {}

    # Fallback/enrichment from ~/.claude/projects/<slug>/*.jsonl
    if proj_dir and proj_dir.is_dir():
        # Oldest first, so a replayed API call is owned by the session where it happened.
        all_jsonl = sorted(proj_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        if token_acc is not None:
            counted: set = set()
            for jpath in all_jsonl:
                subs = sorted((proj_dir / jpath.stem / "subagents").glob("*.jsonl"))
                token_acc.append(
                    _parse_claude_tokens(jpath, jpath.stem, jpath.stem[:12], subs, counted, project_root=project_root)
                )
        for jpath in all_jsonl[::-1][:_MAX_LISTED_SESSIONS]:
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
            parsed = _parse_claude_jsonl(jpath, sess.title, project_root=project_root)
            tok_state = _TOKEN_FILE_CACHE.get(f"claude:{jpath}") or {}
            sess.title = parsed["title"] or tok_state.get("title") or sess.title
            sess.recent_tools = list(parsed["tools"])
            sub_merged = list(tok_state.get("subagents", []))
            for sb in parsed["subagents"]:
                if sb not in sub_merged:
                    sub_merged.append(sb)
            sess.subagents = sub_merged[-16:]
            wf_merged = list(tok_state.get("workflows", []))
            for w in parsed["workflows"]:
                if w not in wf_merged:
                    wf_merged.append(w)
            sess.workflows = wf_merged[-12:]
            tf_merged = list(tok_state.get("touched_files", []))
            for tf in parsed["touched_files"]:
                if tf not in tf_merged:
                    tf_merged.append(tf)
            sess.touched_files = tf_merged[-25:]
            sess.activities = list(parsed["activities"])
            sess.pending_reason = str(parsed["pending_reason"] or "")
            sess.voice_active = bool(parsed["voice_active"])
            sess.last_assistant_text = str(parsed["last_assistant_text"] or "")
            inline_by_sid[sid] = list(parsed["inline_tasks"])
            meta = str(parsed["meta"] or "")
            if meta:
                sess.meta = f"{sess.meta} · {meta}" if sess.meta else meta
            sess.updated_at = max(sess.updated_at, jpath.stat().st_mtime)
            if sess.pending_reason and (time.time() - sess.updated_at) <= _STALE_PENDING_SECONDS:
                sess.status = "pending"
            else:
                sess.pending_reason = ""

    for sid, sess in sessions_by_id.items():
        sess.tasks = _collect_claude_tasks(
            sid,
            claude_home,
            proj_dir=proj_dir,
            inline_tasks=inline_by_sid.get(sid, ()),
        )
        for tk in sess.tasks:
            if tk.kind == "subagent" and tk.title not in sess.subagents:
                sess.subagents.append(tk.title)
        for member in team_members.get(sid, ()):
            if member not in sess.subagents:
                sess.subagents.append(member)
        for prefix, mlist in team_members.items():
            if sid != prefix and sid.startswith(prefix):
                for member in mlist:
                    if member not in sess.subagents:
                        sess.subagents.append(member)
        if not sess.pending_reason and any(t.status in ("running", "in_progress") for t in sess.tasks):
            if sess.status in ("recent", "idle"):
                sess.status = "running"

    return sorted(sessions_by_id.values(), key=lambda s: s.updated_at, reverse=True)


def _antigravity_workspace_conversations(
    antigravity_home: Path,
    project_root: Path,
) -> Tuple[Optional[set], Dict[str, Tuple[str, str, int, str]], set]:
    """Return `(matching_conv_ids_or_None, {conv_id: (title, app_data_dir, step_count, preview)}, all_indexed_ids)`."""
    db_path = antigravity_home / "conversation_summaries.db"
    if not db_path.is_file():
        return None, {}, set()
    try:
        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=1.0)
        try:
            cols = {c[1] for c in con.execute("PRAGMA table_info(conversation_summaries)").fetchall()}
            has_title = "title" in cols
            has_app_dir = "app_data_dir" in cols
            has_steps = "step_count" in cols
            has_preview = "preview" in cols
            sel = "conversation_id, workspace_uris"
            if has_title:
                sel += ", title"
            if has_app_dir:
                sel += ", app_data_dir"
            if has_steps:
                sel += ", step_count"
            if has_preview:
                sel += ", preview"
            rows = con.execute(f"SELECT {sel} FROM conversation_summaries").fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return None, {}, set()
    root = _normalize_path_str(str(project_root))
    ids = set()
    all_indexed_ids = set()
    meta_map: Dict[str, Tuple[str, str, int, str]] = {}
    for row in rows:
        conv_id = str(row[0] or "")
        if conv_id:
            all_indexed_ids.add(conv_id)
        uris_json = row[1]
        pos = 2
        stitle = str(row[pos] or "").strip() if has_title else ""
        if has_title:
            pos += 1
        app_dir = str(row[pos] or "").strip() if has_app_dir else ""
        if has_app_dir:
            pos += 1
        step_count = int(row[pos] or 0) if has_steps else 0
        if has_steps:
            pos += 1
        preview = str(row[pos] or "").strip() if has_preview else ""
        if conv_id and (stitle or app_dir or step_count or preview):
            meta_map[conv_id] = (stitle, app_dir, step_count, preview)
        try:
            uris = json.loads(uris_json or "[]")
        except ValueError:
            continue
        for uri in uris if isinstance(uris, list) else []:
            if not isinstance(uri, str) or not uri.startswith("file:"):
                continue
            ws = _normalize_path_str(url2pathname(unquote(urlparse(uri).path)))
            if ws == root or ws.startswith(root + "/"):
                ids.add(conv_id)
                break
    return ids, meta_map, all_indexed_ids


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


def _extract_agy_tc_args(tc: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and decode tool call arguments from Antigravity transcript (`arguments` or `args`)."""
    raw = tc.get("arguments")
    if not isinstance(raw, dict):
        raw = tc.get("args")
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(v, str) and len(v) >= 2 and v[0] in ('"', "[", "{"):
            try:
                out[k] = json.loads(v)
                continue
            except ValueError:
                pass
        out[k] = v
    return out


def _summarize_agy_tool_call(tc: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    name = str(tc.get("name") or "tool")
    args = _extract_agy_tc_args(tc)
    if not args:
        return name, None
    if name == "invoke_subagent":
        role = str(args.get("Role") or args.get("Name") or args.get("TypeName") or "subagent").strip()
        return f"subagent: {role}", role
    if name == "define_subagent":
        role = str(args.get("Name") or args.get("Role") or "subagent").strip()
        return f"define_subagent: {role}", None
    if name == "send_message":
        rec = str(args.get("Recipient") or "agent").strip()[:12]
        msg = str(args.get("Message") or "").strip().splitlines()[0][:48] if args.get("Message") else ""
        return (f"send_message -> {rec}: {msg}" if msg else f"send_message -> {rec}"), None
    if name == "swarm":
        act = str(args.get("action") or "swarm").strip()
        wname = str(args.get("name") or "").strip()
        label = f"swarm:{act}" + (f" ({wname})" if wname else "")
        return label, wname or label
    if name == "run_workflow":
        desc = str(args.get("Description") or args.get("ScriptPath") or "workflow").strip()
        return f"run_workflow: {desc[:48]}", None
    for key in ("Path", "TargetFile", "CommandLine", "toolSummary", "query", "Prompt"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            short = Path(val).name if key in ("Path", "TargetFile") else val.strip()[:48]
            return f"{name}: {short}", None
    return name, None


_LOG_CREATED_AT_RE = re.compile(r"Created At:\s*(\S+)")
_LOG_COMPLETED_AT_RE = re.compile(r"Completed At:\s*(\S+)")
_AGY_SYS_MSG_RE = re.compile(
    r"\[Message\]\s+timestamp=\S+\s+sender=([^\s]+)\s+priority=\S+\s+content=(.+)",
    re.DOTALL,
)
_STALE_PENDING_SECONDS = 14400.0  # 4h: older unanswered questions are abandoned, not active pending


def _collect_antigravity_tasks(conv_dir: Path, now_ts: float) -> List[AgentTaskInfo]:
    tasks_dir = conv_dir / ".system_generated" / "tasks"
    if not tasks_dir.is_dir():
        return []
    tasks: List[AgentTaskInfo] = []
    for log_path in sorted(tasks_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            st = log_path.stat()
        except OSError:
            continue
        mtime = st.st_mtime
        ctime = min(st.st_ctime, mtime)
        tail = _cached_by_stat(
            "agy_task_log",
            log_path,
            lambda p=log_path: _read_tail_lines(p, max_bytes=32_768, max_lines=_MAX_TASK_TAIL_LINES),
        )
        started_at = ctime
        updated_at = mtime
        for ln in tail[:6]:
            m_c = _LOG_CREATED_AT_RE.search(ln)
            if m_c:
                started_at = _parse_timestamp(m_c.group(1), fallback=started_at)
            m_f = _LOG_COMPLETED_AT_RE.search(ln)
            if m_f:
                updated_at = _parse_timestamp(m_f.group(1), fallback=updated_at)
        status = "running" if (now_ts - mtime) < _ACTIVE_TASK_WINDOW_SECONDS else "finished"
        tasks.append(
            AgentTaskInfo(
                id=log_path.stem,
                agent="antigravity",
                status=status,
                title=log_path.name,
                session_id=conv_dir.name,
                log_path=log_path,
                started_at=started_at,
                updated_at=max(started_at, updated_at),
                tail_lines=tail,
                kind="task",
            )
        )
    return tasks


def _parse_antigravity_transcript(transcript: Path, conv_id: str, project_root: Path) -> Dict[str, Any]:
    def _build() -> Dict[str, Any]:
        tools: List[str] = []
        subagents: List[str] = []
        workflows: List[str] = []
        touched_files: List[str] = []
        inline_tasks: List[AgentTaskInfo] = []
        activities: List[AgentActivityItem] = []
        title = conv_id[:12]
        last_step_status = ""
        pending_reason = ""
        last_assistant_text = ""

        try:
            fallback_ts = transcript.stat().st_mtime
        except OSError:
            fallback_ts = time.time()

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
            step_idx = obj.get("step_index")
            step_type = str(obj.get("type") or "")
            step_status = str(obj.get("status") or "")
            created_at = str(obj.get("created_at") or "")
            step_ts = _parse_timestamp(created_at, fallback=fallback_ts)
            ts_hms = created_at[11:19] if len(created_at) >= 19 else "--:--:--"

            if step_type == "USER_INPUT":
                pending_reason = ""
                if isinstance(obj.get("content"), str):
                    lines_clean = [
                        ln.strip()
                        for ln in obj["content"].splitlines()
                        if ln.strip() and not ln.strip().startswith("<")
                    ]
                    if lines_clean:
                        title = lines_clean[0][:44]
            elif step_type == "SYSTEM_MESSAGE" and isinstance(obj.get("content"), str):
                m_sys = _AGY_SYS_MSG_RE.search(obj["content"])
                if m_sys:
                    sender_id = m_sys.group(1).strip()
                    body_lines = [
                        ln.strip()
                        for ln in m_sys.group(2).splitlines()
                        if ln.strip() and not ln.strip().startswith("<")
                    ]
                    first_body = body_lines[0] if body_lines else ""
                    if "/" not in sender_id:
                        if step_idx == 0 and title == conv_id[:12] and first_body:
                            title = f"↳ {first_body[:40]}"
                        elif first_body:
                            activities.append(
                                AgentActivityItem(
                                    timestamp=ts_hms,
                                    agent="antigravity",
                                    kind="message",
                                    summary=f"recv_message <- {sender_id[:8]}: {first_body[:48]}",
                                )
                            )

            if step_status:
                last_step_status = step_status

            if step_type == "PLANNER_RESPONSE" and isinstance(obj.get("content"), str) and obj["content"].strip():
                last_assistant_text = obj["content"].strip()

            tcs = obj.get("tool_calls") or []
            if step_type == "PLANNER_RESPONSE" and tcs:
                # Reset previous step pending unless a new pending tool call appears in this step
                pending_reason = ""
            for tc_idx, tc in enumerate(tcs):
                if not isinstance(tc, dict):
                    continue
                tname = str(tc.get("name") or "")
                args = _extract_agy_tc_args(tc)
                if tname and tname not in tools:
                    tools.append(tname)
                summary, subagent = _summarize_agy_tool_call(tc)
                if subagent and subagent not in subagents:
                    subagents.append(subagent)
                activities.append(
                    AgentActivityItem(timestamp=ts_hms, agent="antigravity", kind="tool", summary=summary)
                )

                tid = f"step-{step_idx}-{tc_idx}" if step_idx is not None else f"tc-{len(inline_tasks)}"
                if tname == "run_workflow":
                    spath = str(args.get("ScriptPath") or "").strip()
                    desc = str(args.get("Description") or (Path(spath).name if spath else "workflow")).strip()
                    wlabel = f"run_workflow: {desc}"
                    if spath and Path(spath).name not in wlabel:
                        wlabel = f"{wlabel} ({Path(spath).name})"
                    if wlabel not in workflows:
                        workflows.append(wlabel)
                    inline_tasks.append(
                        AgentTaskInfo(
                            id=tid,
                            agent="antigravity",
                            status="finished",
                            title=wlabel,
                            session_id=conv_id,
                            log_path=transcript,
                            started_at=step_ts,
                            updated_at=step_ts,
                            tail_lines=[wlabel],
                            kind="workflow",
                        )
                    )
                elif tname == "schedule":
                    sprompt = str(args.get("Prompt") or "timer").strip()[:40]
                    inline_tasks.append(
                        AgentTaskInfo(
                            id=tid,
                            agent="antigravity",
                            status="running",
                            title=f"schedule: {sprompt}",
                            session_id=conv_id,
                            log_path=transcript,
                            started_at=step_ts,
                            updated_at=step_ts,
                            tail_lines=[f"[schedule] {sprompt}"],
                            kind="cron",
                        )
                    )
                elif tname in ("write_file", "edit_file", "replace_file_content", "multi_replace_file_content", "write_to_file"):
                    raw_p = str(args.get("Path") or args.get("TargetFile") or "").strip()
                    if raw_p:
                        rel_p = _relativize_project_path(raw_p, project_root)
                        if rel_p and rel_p not in touched_files:
                            touched_files.append(rel_p)
                    art_meta = args.get("ArtifactMetadata")
                    if isinstance(art_meta, dict) and art_meta.get("RequestFeedback"):
                        pending_reason = f"Feedback requerido: {Path(raw_p).name if raw_p else 'artefacto'}"
                elif tname == "ask_question":
                    q_txt = _extract_first_question(args.get("questions"))
                    pending_reason = f"Pregunta: {q_txt}" if q_txt else "Pregunta al usuario"

        return {
            "title": title,
            "tools": tools[-12:],
            "subagents": subagents[-12:],
            "workflows": workflows[-12:],
            "touched_files": touched_files[-25:],
            "inline_tasks": inline_tasks[-15:],
            "activities": activities[-20:],
            "last_step_status": last_step_status,
            "pending_reason": pending_reason,
            "last_assistant_text": last_assistant_text,
        }

    return _cached_by_stat("agy_transcript", transcript, _build)


def _collect_antigravity_sessions(
    project_root: Path,
    antigravity_home: Path,
    token_acc: Optional[List[Tuple[SessionTokenSummary, Dict[str, TokenConsumer]]]] = None,
) -> List[AgentSessionInfo]:
    seen_file = project_root / AOS_DIR_NAME / "native" / "antigravity-seen.txt"
    seen_ids = set(seen_file.read_text(encoding="utf-8", errors="replace").split()) if seen_file.is_file() else set()

    # Scan primary `antigravity/` (Antigravity 2.0 / IDE) and sibling `antigravity-cli/` (`agy` CLI)
    homes: List[Path] = [antigravity_home]
    cli_home: Optional[Path] = None
    if antigravity_home.name == "antigravity":
        candidate_cli = antigravity_home.parent / "antigravity-cli"
        if candidate_cli.is_dir():
            cli_home = candidate_cli
            homes.append(candidate_cli)

    now_ts = time.time()
    workspace_ids_union: Optional[set] = None
    all_indexed_ids: set = set()
    summary_meta: Dict[str, Tuple[str, str, int, str]] = {}
    for h in homes:
        ws_ids, h_meta, h_all = _antigravity_workspace_conversations(h, project_root)
        all_indexed_ids |= h_all
        if ws_ids is not None:
            workspace_ids_union = ws_ids if workspace_ids_union is None else (workspace_ids_union | ws_ids)
        for cid, (stitle, app_dir, scount, preview) in h_meta.items():
            prev_t, prev_d, prev_s, prev_p = summary_meta.get(cid, ("", "", 0, ""))
            summary_meta[cid] = (stitle or prev_t, prev_d or app_dir, max(scount, prev_s), preview or prev_p)

    conv_dirs_by_id: Dict[str, Tuple[Path, str]] = {}
    try:
        for h in homes:
            bdir = h / "brain"
            if not bdir.is_dir():
                continue
            default_tag = "agy-cli" if h == cli_home else "agy-ide"
            if workspace_ids_union is not None:
                cands = [bdir / cid for cid in workspace_ids_union if (bdir / cid).is_dir()]
                # Also recover recent unindexed/evicted sessions (e.g. parallel IDE+CLI summary eviction)
                # without misattributing sessions already indexed under another workspace.
                unindexed = sorted(
                    (p for p in bdir.iterdir() if p.is_dir() and p.name not in all_indexed_ids),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                for p in unindexed[:_MAX_LISTED_SESSIONS]:
                    if _antigravity_matches_project(p, project_root, seen_ids):
                        cands.append(p)
            else:
                recent = sorted((p for p in bdir.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
                cands = [p for p in recent[:_MAX_LISTED_SESSIONS] if _antigravity_matches_project(p, project_root, seen_ids)]
            for cdir in cands:
                # Track actual DB presence first so we know accurately whether `agy --conversation` can load directly
                cid = cdir.name
                if cli_home is not None and (cli_home / "conversations" / f"{cid}.db").is_file():
                    tag = "agy-cli"
                elif (antigravity_home / "conversations" / f"{cid}.db").is_file():
                    tag = "agy-ide"
                else:
                    tag = default_tag
                prev = conv_dirs_by_id.get(cid)
                if prev is None:
                    conv_dirs_by_id[cid] = (cdir, tag)
                else:
                    try:
                        prev_has = (prev[0] / ".system_generated" / "logs" / "transcript.jsonl").is_file()
                        curr_has = (cdir / ".system_generated" / "logs" / "transcript.jsonl").is_file()
                        if (curr_has and not prev_has) or (curr_has == prev_has and cdir.stat().st_mtime > prev[0].stat().st_mtime):
                            conv_dirs_by_id[cid] = (cdir, tag)
                    except OSError:
                        pass

        def _pair_mtime(pair: Tuple[Path, str]) -> float:
            cdir = pair[0]
            cid = cdir.name
            best = 0.0
            for cand in (
                cdir,
                cdir / ".system_generated" / "logs" / "transcript.jsonl",
                antigravity_home / "conversations" / f"{cid}.db",
                (cli_home / "conversations" / f"{cid}.db") if cli_home is not None else None,
            ):
                if cand is not None:
                    try:
                        best = max(best, cand.stat().st_mtime)
                    except OSError:
                        pass
            return best

        matched_pairs = sorted(conv_dirs_by_id.values(), key=_pair_mtime, reverse=True)
    except OSError:
        return []

    if not matched_pairs:
        return []

    if token_acc is not None:
        for conv_dir, _ in matched_pairs:
            transcript = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
            if transcript.is_file():
                token_acc.append(_parse_antigravity_tokens(transcript, conv_dir.name, conv_dir.name[:12]))

    sessions: List[AgentSessionInfo] = []
    for conv_dir, src_tag in matched_pairs[:_MAX_LISTED_SESSIONS]:
        transcript = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
        tools: List[str] = []
        subagents: List[str] = []
        workflows: List[str] = []
        touched_files: List[str] = []
        inline_tasks: List[AgentTaskInfo] = []
        activities: List[AgentActivityItem] = []
        title = conv_dir.name[:12]
        sum_title, app_dir, step_count, sum_preview = summary_meta.get(conv_dir.name, ("", "", 0, ""))
        last_status = "idle"
        pending_reason = ""
        last_assistant_text = ""
        latest_mtime = conv_dir.stat().st_mtime
        for h in homes:
            db_cand = h / "conversations" / f"{conv_dir.name}.db"
            if db_cand.is_file():
                try:
                    latest_mtime = max(latest_mtime, db_cand.stat().st_mtime)
                except OSError:
                    pass

        if transcript.is_file():
            latest_mtime = max(latest_mtime, transcript.stat().st_mtime)
            parsed = _parse_antigravity_transcript(transcript, conv_dir.name, project_root)
            tok_state = _TOKEN_FILE_CACHE.get(f"antigravity:{transcript}") or {}
            title = parsed["title"]
            if title == conv_dir.name[:12] and tok_state.get("title"):
                title = str(tok_state["title"])
            if title == conv_dir.name[:12] and sum_title:
                title = sum_title[:44]
            tools = list(parsed["tools"])
            sub_merged = list(tok_state.get("subagents", []))
            for sb in parsed["subagents"]:
                if sb not in sub_merged:
                    sub_merged.append(sb)
            subagents = sub_merged[-16:]
            wf_merged = list(tok_state.get("workflows", []))
            for wf in parsed["workflows"]:
                if wf not in wf_merged:
                    wf_merged.append(wf)
            workflows = wf_merged[-12:]
            touched_files = list(parsed["touched_files"])
            inline_tasks = list(parsed["inline_tasks"])
            activities = list(parsed["activities"])
            pending_reason = str(parsed["pending_reason"] or "")
            last_assistant_text = str(parsed["last_assistant_text"] or "")
            step_status = str(parsed["last_step_status"] or "")
            if pending_reason and (now_ts - latest_mtime) <= _STALE_PENDING_SECONDS:
                last_status = "pending"
            else:
                pending_reason = ""
                if step_status and step_status != "DONE":
                    last_status = "running"
                elif step_status == "DONE":
                    last_status = "active" if (now_ts - latest_mtime) < 60 else "idle"

        log_tasks = _collect_antigravity_tasks(conv_dir, now_ts)
        tasks = sorted(log_tasks + inline_tasks, key=lambda t: t.updated_at, reverse=True)
        if not pending_reason and any(t.status == "running" for t in log_tasks):
            last_status = "running"

        if src_tag != "agy-cli" and app_dir == "antigravity-cli" and cli_home is not None and (cli_home / "conversations" / f"{conv_dir.name}.db").is_file():
            src_tag = "agy-cli"

        # Skip truly empty transient CLI stubs (no transcript, no tasks, no summary title/preview, 0 steps)
        if src_tag == "agy-cli" and not transcript.is_file() and not tasks and not sum_title and not sum_preview and step_count <= 0:
            continue

        if title == conv_dir.name[:12]:
            if sum_title:
                title = sum_title[:44]
            elif sum_preview:
                first_prev = next((ln.strip() for ln in sum_preview.splitlines() if ln.strip()), "")
                if first_prev:
                    title = first_prev[:44]
            elif step_count > 0:
                title = f"CLI ({step_count} steps) · {conv_dir.name[:8]}"

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
                meta=f"{len(tasks)} task(s) · {src_tag}",
                pending_reason=pending_reason,
                workflows=workflows[-12:],
                touched_files=touched_files[-25:],
                last_assistant_text=last_assistant_text,
                summary_title=sum_title,
            )
        )

    return sorted(sessions, key=lambda s: s.updated_at, reverse=True)


def collect_telemetry(
    project_root: Path,
    claude_home: Optional[Path] = None,
    antigravity_home: Optional[Path] = None,
    prev_snapshot: Optional[TelemetrySnapshot] = None,
    include_slow: bool = True,
    include_git: bool = True,
    force_deps: bool = False,
) -> TelemetrySnapshot:
    """Collect a full read-only snapshot of `.aos/`, Git, and local AI sessions.

    When ``include_slow`` is False, expensive harness checks (`doctor`,
    `missing_dependencies`, `native_status`) are reused from ``prev_snapshot``
    (or deferred on fast first paint) so high-frequency TUI polling stays lightweight.
    When ``include_git`` is False and ``prev_snapshot`` is provided, the previous
    Git snapshot is reused to avoid spawning `git` when not viewing Git/Overview.
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

    if include_slow:
        doctor_findings = collect_findings(root)
        status_report = build_report(root, findings=doctor_findings)
        native_tools = native_status(root)
        now_ts = time.time()
        deps_key = str(root)
        cached_deps = _DEPS_CACHE.get(deps_key)
        if not force_deps and cached_deps is not None and (now_ts - cached_deps[0]) < _DEPS_CACHE_TTL_SECONDS:
            missing_deps = list(cached_deps[1])
        else:
            missing_deps = missing_dependencies(root)
            _DEPS_CACHE[deps_key] = (now_ts, list(missing_deps))
    else:
        doctor_findings = prev_snapshot.doctor_findings if prev_snapshot is not None else []
        native_tools = prev_snapshot.native_tools if prev_snapshot is not None else {}
        missing_deps = prev_snapshot.missing_deps if prev_snapshot is not None else []
        status_report = build_report(root, findings=doctor_findings)

    if include_git or prev_snapshot is None:
        git_snap = _collect_git_snapshot(root)
    else:
        git_snap = prev_snapshot.git

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
        if sess.status == "pending" and (
            old_s is None or old_s.status != "pending" or old_s.pending_reason != sess.pending_reason
        ):
            reason = sess.pending_reason or "Esperando acción del usuario"
            events.append(
                LiveEvent(
                    timestamp=ts,
                    level="warn",
                    source=sess.tool,
                    message=f"PENDING ({sess.title}): {reason}",
                )
            )

    return events
