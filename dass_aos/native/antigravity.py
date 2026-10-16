"""Antigravity 2.0: skills and a PreInvocation hook that emulates session start (ADR-005).

No subagent files (the runtime does not load them): roles are delegated with `define_subagent`, as the
managed block of GEMINI.md says. MCP is global (~/.gemini/config/mcp_config.json), never per project.
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from typing import Dict, Iterable, List

from ..constants import AOS_DIR_NAME
from .base import JsonMerge, NativeAdapter
from .sources import Skill

SEEN_KEEP = 50  # ponytail: last N conversation ids, older ones would get the refresh again


class AntigravityAdapter(NativeAdapter):
    TOOL = "antigravity"
    VERIFIED = {
        "date": "2026-10-16",
        "version": "2.0",
        "sources": [
            "~/.gemini/antigravity/builtin/skills/agy-customizations/docs/skills.md",
            "~/.gemini/antigravity/builtin/skills/agy-customizations/docs/hooks.md",
            "~/.gemini/antigravity/builtin/skills/agy-customizations/docs/rules.md",
            "~/.gemini/antigravity/builtin/skills/agy-customizations/docs/mcp_servers.md",
        ],
    }
    ENFORCEMENT = {
        "tools": "convention (define_subagent + enable_write_tools)",
        "session_start": "native-emulated (PreInvocation, once per conversation)",
        "mcp": "user-level (~/.gemini/config/mcp_config.json)",
    }

    def skills(self, skills: List[Skill]) -> Dict[str, str]:
        return {f".agents/skills/{s.name}/SKILL.md": self.skill_md(s) for s in skills}

    def hooks(self) -> List[JsonMerge]:
        # cwd is the folder holding hooks.json (.agents/); `cmd /c` on Windows, `sh -c` elsewhere
        command = "cd .. && (aos refresh --hook antigravity || python -m dass_aos refresh --hook antigravity)"
        value = {"PreInvocation": [{"type": "command", "command": command, "timeout": 30}]}
        return [JsonMerge(".agents/hooks.json", ["dass-aos-refresh"], value, "dass-aos-refresh")]

    def registered_mcp(self) -> Iterable[str]:
        config = self.load_json(Path.home() / ".gemini" / "config" / "mcp_config.json")
        return [f"user:{s}" for s in config.get("mcpServers", {})]


def refresh_hook(project_root: Path, stdin: bytes) -> str:
    """`aos refresh --hook antigravity`: inject the session refresh once per conversation. Never fails."""
    from ..memory import run_memory_refresh

    try:
        # Bytes, not sys.stdin text: Windows decodes stdin as cp1252 and shells may prepend a BOM
        conversation = json.loads(stdin.decode("utf-8-sig") or "{}").get("conversationId")
        seen_file = project_root / AOS_DIR_NAME / "native" / "antigravity-seen.txt"
        seen = seen_file.read_text(encoding="utf-8").split() if seen_file.exists() else []
        if not conversation or conversation in seen:
            return "{}"
        with redirect_stdout(io.StringIO()):
            text = run_memory_refresh(project_root)
        seen_file.parent.mkdir(parents=True, exist_ok=True)
        seen_file.write_text("\n".join((seen + [conversation])[-SEEN_KEEP:]) + "\n", encoding="utf-8")
        return json.dumps({"injectSteps": [{"ephemeralMessage": text}]}, ensure_ascii=False)
    except Exception:  # a hook must never break the agent loop
        return "{}"
