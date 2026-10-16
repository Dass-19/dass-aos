"""Constants and configuration defaults for DASS-AOS."""
from __future__ import annotations

import sys
from pathlib import Path

VERSION = "0.6.0"

# Managed block markers
MANAGED_START = "<!-- DASS-AOS-MANAGED-START -->"
MANAGED_END = "<!-- DASS-AOS-MANAGED-END -->"

# Backward compatibility markers
LEGACY_MANAGED_START = "<!-- AI-AGENT-AOS-MANAGED-START -->"
LEGACY_MANAGED_END = "<!-- AI-AGENT-AOS-MANAGED-END -->"

# Instruction file each AI tool reads. A project only gets the files of the tools it uses (.aos/config.json "tools").
# Antigravity also reads AGENTS.md, but GEMINI.md is enough and carries its delegation rule.
TOOL_FILES = {
    "claude-code": "CLAUDE.md",
    "antigravity": "GEMINI.md",
    "gemini-cli": "GEMINI.md",
    "codex": "AGENTS.md",
    "opencode": "AGENTS.md",
    "cursor": ".cursorrules",
    "windsurf": ".windsurfrules",
}
# What in a repo shows that a tool is already in use (for `aos init` without arguments)
TOOL_SIGNS = {
    "claude-code": [".claude", "CLAUDE.md"],
    # Not plain `.agents/`: `.agents/skills/` is the shared agentskills location (Codex, playwright-cli --skills=agents)
    "antigravity": [".agents/hooks.json", ".agents/skills.json", ".agents/plugins.json", ".agents/plugins",
                    ".agents/rules", ".agent", "_agents", "_agent"],
    "gemini-cli": [".gemini", "GEMINI.md"],
    "codex": [".codex", "AGENTS.md"],
    "opencode": [".opencode", "opencode.json"],
    "cursor": [".cursor", ".cursorrules"],
    "windsurf": [".windsurf", ".windsurfrules"],
}
INSTRUCTION_FILES = sorted(set(TOOL_FILES.values()))
RULE_FILES = [".cursorrules", ".windsurfrules"]

# Default project state directory name
AOS_DIR_NAME = ".aos"

# Templates shipped inside the package; layout mirrors .aos/
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# Safe console output setup (avoids cp1252 UnicodeEncodeError on Windows)
def configure_utf8_output() -> None:
    """Ensure stdout and stderr use UTF-8 without crashing on Windows cp1252."""
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
