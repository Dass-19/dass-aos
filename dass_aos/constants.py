"""Constants and configuration defaults for DASS-AOS."""
from __future__ import annotations

import sys
from pathlib import Path

VERSION = "0.4.0"

# Managed block markers
MANAGED_START = "<!-- DASS-AOS-MANAGED-START -->"
MANAGED_END = "<!-- DASS-AOS-MANAGED-END -->"

# Backward compatibility markers
LEGACY_MANAGED_START = "<!-- AI-AGENT-AOS-MANAGED-START -->"
LEGACY_MANAGED_END = "<!-- AI-AGENT-AOS-MANAGED-END -->"

# Target agent instruction files
AGENT_FILES = ["CLAUDE.md", "AGENTS.md", "GEMINI.md"]
RULE_FILES = [".cursorrules", ".windsurfrules"]

# Default project state directory name
AOS_DIR_NAME = ".aos"

# Engine root directory (where dass_aos package lives)
ENGINE_ROOT = Path(__file__).resolve().parent.parent

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
