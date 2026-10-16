"""Read the rendered .aos/ (base + .local.md, already merged by `aos sync`) as plain data."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from ..constants import AOS_DIR_NAME
from ..sync import GENERATED_MARKER, get_available_skills


@dataclass
class Role:
    name: str
    description: str
    tools_allowed: List[str]
    body: str


@dataclass
class Skill:
    name: str
    description: str
    body: str


def split_frontmatter(text: str):
    text = text.replace("\r\n", "\n").lstrip("﻿")  # Notepad / PowerShell 5.1 write a BOM
    if not text.startswith("---\n"):
        return "", text
    parts = re.split(r"^---[ \t]*$\n?", text, maxsplit=2, flags=re.M)
    if len(parts) < 3:
        raise ValueError("frontmatter sin línea de cierre '---'")
    return parts[1], parts[2]


def field(front: str, name: str):
    m = re.search(rf"^{name}:[ \t]*(.*)$", front, re.M)  # \s* would run into the next line
    if not m:
        return None
    raw = m.group(1).strip()
    try:
        return json.loads(raw)
    except ValueError:
        return raw.strip('"')


def strip_marker(body: str) -> str:
    return "\n".join(line for line in body.split("\n") if GENERATED_MARKER not in line).strip("\n") + "\n"


def read_doc(path: Path):
    try:
        return split_frontmatter(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from exc


def roles(project_root: Path) -> List[Role]:
    out = []
    for p in sorted((project_root / AOS_DIR_NAME / "agents").glob("*.md")):
        if p.stem.endswith(".local"):
            continue
        front, body = read_doc(p)
        out.append(Role(p.stem, field(front, "description") or "", field(front, "tools_allowed") or [], strip_marker(body)))
    return out


def skills(project_root: Path) -> List[Skill]:
    """Specs that apply to the project; adapt-native is the fallback for tools without a generator."""
    applicable = set(get_available_skills(project_root))
    out = []
    for p in sorted((project_root / AOS_DIR_NAME / "skills" / "specs").glob("*.md")):
        if p.stem.endswith(".local") or p.stem == "adapt-native" or p.stem not in applicable:
            continue
        front, body = read_doc(p)
        out.append(Skill(p.stem, field(front, "description") or "", strip_marker(body)))
    return out


def mcp_servers(project_root: Path) -> Dict[str, dict]:
    path = project_root / AOS_DIR_NAME / "mcp-config.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("mcpServers", {})
