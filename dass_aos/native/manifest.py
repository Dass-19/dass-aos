"""Manifest .aos/native/<tool>.json and staleness detection (ADR-004, ADR-005)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict

from ..constants import AOS_DIR_NAME
from ..sync import get_available_skills

# Sources that the native generators translate; a change here means native artifacts are stale
NATIVE_SOURCES = ["agents", "skills", "hooks", "mcp-config.json"]


def native_source_hash(project_root: Path) -> str:
    """Hash of everything adapt-native reads, plus which skills currently apply."""
    aos_dir = project_root / AOS_DIR_NAME
    h = hashlib.sha256()
    for name in NATIVE_SOURCES:
        src = aos_dir / name
        files = [src] if src.is_file() else sorted(src.rglob("*")) if src.is_dir() else []
        for p in files:
            if p.is_file() and "__pycache__" not in p.parts:
                h.update(p.relative_to(aos_dir).as_posix().encode("utf-8"))
                h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    h.update("\n".join(get_available_skills(project_root)).encode("utf-8"))
    return h.hexdigest()[:16]


def manifest_path(project_root: Path, tool: str) -> Path:
    return project_root / AOS_DIR_NAME / "native" / f"{tool}.json"


def read_manifest(project_root: Path, tool: str) -> dict:
    try:
        return json.loads(manifest_path(project_root, tool).read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def native_status(project_root: Path) -> Dict[str, str]:
    """Tool -> status for each .aos/native/<tool>.json manifest."""
    from . import ADAPTERS  # registry imports adapters, which import this module

    current = native_source_hash(project_root)
    status = {}
    for manifest in sorted((project_root / AOS_DIR_NAME / "native").glob("*.json")):
        try:
            ok = json.loads(manifest.read_text(encoding="utf-8")).get("source_hash") == current
        except (ValueError, OSError):
            ok = False
        fix = f"ejecuta `aos adapt-native {manifest.stem}`" if manifest.stem in ADAPTERS else "ejecuta la skill adapt-native"
        status[manifest.stem] = "al día" if ok else f"DESACTUALIZADO: {fix}"
    return status
