"""Safe writes for generated native files (ADR-004 §writing rules). Pure helpers: no tool knowledge."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # avoids importing the backup module at runtime just for a type hint
    from ..backup import Snapshots

MARKER = "DASS-AOS-GENERATED"


class UnreadableJson(Exception):
    """A user config file that is not valid JSON of the expected shape: never rewritten."""


def is_generated(path: Path) -> bool:
    return path.exists() and MARKER in path.read_text(encoding="utf-8")


def write_text(path: Path, text: str, dry_run: bool, snapshots: Optional["Snapshots"] = None) -> Optional[str]:
    """Write LF text if it changed. Returns 'creado' / 'actualizado' / None (no change)."""
    old = path.read_text(encoding="utf-8").replace("\r\n", "\n") if path.exists() else None
    if old == text:
        return None
    if not dry_run:
        if snapshots:
            snapshots.snapshot(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    return "creado" if old is None else "actualizado"


def merge_json(
    path: Path,
    keypath: List[str],
    value: Any,
    owns: Optional[Callable[[Any], bool]],
    dry_run: bool,
    snapshots: Optional["Snapshots"] = None,
) -> Optional[str]:
    """Set data[keypath] = value keeping everything else.

    With `owns`, the target is a list: replace the items `owns` matches (ours) with `value`'s, keep the rest.
    A dict value is merged shallowly so the user's keys (e.g. `"enabled": false`) survive.
    Raises UnreadableJson instead of rewriting a file it cannot parse.
    """
    try:
        # utf-8-sig: PowerShell 5.1 `Set-Content -Encoding utf8` writes a BOM
        data = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
        node = data
        for key in keypath[:-1]:
            node = node.setdefault(key, {})
        last = keypath[-1]
        current = node.get(last)
        if owns is not None:
            new = [item for item in (current or []) if not owns(item)] + value
        elif isinstance(value, dict) and isinstance(current, dict):
            new = {**current, **value}
        else:
            new = value
    except (ValueError, AttributeError, TypeError) as exc:
        raise UnreadableJson(path) from exc
    if node.get(last) == new:
        return None
    node[last] = new
    if not dry_run:
        if snapshots:
            snapshots.snapshot(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return "fusionado"


def gitignore_block(project_root: Path, tool: str, paths: List[str], dry_run: bool) -> Optional[str]:
    """Replace only this tool's marked block; never touch other tools' blocks."""
    start = f"# >>> DASS-AOS adapt-native: {tool} (generado, no editar) >>>"
    end = f"# <<< DASS-AOS adapt-native: {tool} <<<"
    gi = project_root / ".gitignore"
    raw = gi.read_bytes().decode("utf-8") if gi.exists() else ""
    eol = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n")
    block = "\n".join([start, *sorted(paths), end])
    i = text.find(start)
    j = text.find(end, i) if i != -1 else -1
    if i != -1 and j == -1:
        return "sin cierre"  # replacing up to a later end marker would drop the user's lines in between
    if i != -1:
        new = text[:i] + block + text[j + len(end):]
    else:
        new = text.rstrip("\n") + ("\n\n" if text.strip() else "") + block + "\n"
    if new == text:
        return None
    if not dry_run:
        gi.write_bytes(new.replace("\n", eol).encode("utf-8"))
    return "actualizado"
