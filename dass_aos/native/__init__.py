"""Deterministic native generators per AI tool (ADR-005). Adding a tool = one module + one line here."""
from __future__ import annotations

from pathlib import Path

from .antigravity import AntigravityAdapter
from .base import NativeAdapter
from .claude import ClaudeAdapter

ADAPTERS = {"claude-code": ClaudeAdapter, "antigravity": AntigravityAdapter}


def get_adapter(tool: str, project_root: Path) -> NativeAdapter:
    if tool not in ADAPTERS:
        raise ValueError(
            f"herramienta sin generador: '{tool}'. Soportadas: {', '.join(sorted(ADAPTERS))}. "
            "Para otras, ejecuta la skill adapt-native (.aos/skills/specs/adapt-native.md) desde esa herramienta."
        )
    return ADAPTERS[tool](project_root)
