"""Interactive Terminal UI (`aos tui`) for DASS-AOS.

Textual is imported lazily via `_import_textual()` so the rest of `dass-aos`
continues working with zero mandatory runtime dependencies (ADR-010).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Tuple


def _import_textual() -> Tuple[type, ...]:
    """Import Textual lazily; raises ImportError if `[tui]` is not installed."""
    import textual  # noqa: F401
    from textual.app import App

    return (App,)


def run_tui(project_root: Path, interval: float = 1.5) -> int:
    """Launch the interactive DASS-AOS TUI dashboard."""
    try:
        _import_textual()
    except ImportError:
        print(
            "[aos ERROR]: La TUI interactiva requiere el extra opcional `[tui]` (Textual).\n"
            "Instálalo con:\n"
            '  pip install "dass-aos[tui]"',
            file=sys.stderr,
        )
        return 1

    from .app import AosTuiApp

    app = AosTuiApp(project_root=project_root.resolve(), interval=max(0.5, float(interval)))
    app.run()
    return 0


__all__ = ["_import_textual", "run_tui"]
