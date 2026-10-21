"""Claude Code: subagents, skills, SessionStart hook; MCP reused from the user's config (ADR-005)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List

from .base import JsonMerge, NativeAdapter
from .sources import Role, Skill

# Neutral value -> Claude Code tools it grants. A role is restricted with `disallowedTools` (what it lacks)
# instead of a `tools` allowlist, because an allowlist also drops every MCP tool not listed.
GRANTS = {
    "read": ["Read"],
    "search": ["Grep", "Glob"],
    "edit": ["Edit", "NotebookEdit"],
    "write": ["Write"],
    "shell": ["Bash", "PowerShell"],
    "web": ["WebFetch", "WebSearch"],
}
REFRESH = "cd \"$CLAUDE_PROJECT_DIR\" && { aos refresh 2>/dev/null || python -m dass_aos refresh 2>/dev/null || py -m dass_aos refresh; } ; exit 0"


def _only_our_hooks(group) -> bool:
    """A SessionStart group is ours only if every hook in it is: a mixed group keeps the user's hooks."""
    hooks = group.get("hooks") if isinstance(group, dict) else None
    return bool(hooks) and all("dass_aos refresh" in str(h.get("command", "")) for h in hooks if isinstance(h, dict))


class ClaudeAdapter(NativeAdapter):
    TOOL = "claude-code"
    VERSION_COMMAND = ["claude", "--version"]
    VERIFIED = {
        "date": "2026-10-16",
        "sources": [
            "https://code.claude.com/docs/en/sub-agents",
            "https://code.claude.com/docs/en/hooks",
            "https://code.claude.com/docs/en/skills",
        ],
    }
    ENFORCEMENT = {
        "tools": "native (disallowedTools)",
        "shell_prefix": "convention",
        "mcp_subset": "convention",
        "session_start": "native",
    }

    def agents(self, roles: List[Role]) -> Dict[str, str]:
        out = {}
        for role in roles:
            kinds = {t.split(":", 1)[0] for t in role.tools_allowed}
            blocked = [tool for kind, tools in GRANTS.items() if kind not in kinds for tool in tools]
            notes = []
            prefixes = [t.split(":", 1)[1] for t in role.tools_allowed if t.startswith("shell:")]
            if prefixes and "shell" not in role.tools_allowed:
                notes.append(f"- Bash/PowerShell solo para: {', '.join(f'`{p}`' for p in prefixes)} (convención: Claude Code no restringe prefijos por subagente).")
            mcps = [t.split(":", 1)[1] for t in role.tools_allowed if t.startswith("mcp:")]
            if mcps:
                notes.append(f"- Servidores MCP previstos: {', '.join(f'`{m}`' for m in mcps)}; no uses otros (convención).")
            head = ["---", f"name: {role.name}", f"description: {json.dumps(role.description, ensure_ascii=False)}"]
            if blocked:
                head.append(f"disallowedTools: {', '.join(blocked)}")
            text = "\n".join([*head, "---", self.marker(f".aos/agents/{role.name}.md"), "", role.body.rstrip("\n")]) + "\n"
            if notes:
                text += "\n## Restricciones de herramientas (aos adapt-native)\n" + "\n".join(notes) + "\n"
            out[f".claude/agents/{role.name}.md"] = text
        return out

    def skills(self, skills: List[Skill]) -> Dict[str, str]:
        return {f".claude/skills/{s.name}/SKILL.md": self.skill_md(s) for s in skills}

    def hooks(self) -> List[JsonMerge]:
        entry = {
            "matcher": "startup|resume|clear|compact",
            "hooks": [{"type": "command", "shell": "bash", "timeout": 30, "command": REFRESH}],
        }
        return [JsonMerge(".claude/settings.local.json", ["hooks", "SessionStart"], [entry], "hooks.SessionStart",
                          owns=_only_our_hooks)]

    def registered_mcp(self) -> Iterable[str]:
        user = self.load_json(Path.home() / ".claude.json")
        servers = set(user.get("mcpServers", {}))
        # Claude Code keys projects as C:/x, c:/x or C:\x depending on how it was opened
        me = self.root.resolve().as_posix().casefold()
        me_raw = self.root.as_posix().casefold()
        for key, project in user.get("projects", {}).items():
            k_norm = key.replace("\\", "/").casefold()
            try:
                k_resolved = Path(key).resolve().as_posix().casefold()
            except Exception:
                k_resolved = k_norm
            if k_norm == me_raw or k_resolved == me:
                servers |= set(project.get("mcpServers", {}))
        servers |= set(self.load_json(self.root / ".mcp.json").get("mcpServers", {}))
        plugins = self.load_json(Path.home() / ".claude" / "settings.json").get("enabledPlugins", {})
        return [f"user:{s}" for s in servers] + [f"plugin:{p.split('@')[0]}" for p, on in plugins.items() if on]
