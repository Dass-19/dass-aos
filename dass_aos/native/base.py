"""NativeAdapter: orchestrates one tool's generation. Adapters only describe *what*; this writes it (ADR-005)."""
from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from ..sync import validate_tools_allowed
from . import files, sources
from .manifest import manifest_path, native_source_hash, read_manifest


@dataclass
class JsonMerge:
    """A sensitive config change (hooks, permissions): only written with --yes."""
    path: str  # relative to the project root
    keypath: List[str]
    value: Any
    label: str  # manifest entry is "<path>#<label>"
    owns: Optional[Callable[[Any], bool]] = None  # set when the target is a shared list


class NativeAdapter:
    TOOL = ""
    VERIFIED: Dict[str, Any] = {}  # date and sources the format was checked against
    VERSION_COMMAND: List[str] = []
    ENFORCEMENT: Dict[str, str] = {}

    def __init__(self, project_root: Path):
        self.root = project_root
        self.warnings: List[str] = []

    # ---- what each tool implements (empty when it does not apply) ------------------------------
    def agents(self, roles: List[sources.Role]) -> Dict[str, str]:
        return {}

    def skills(self, skills: List[sources.Skill]) -> Dict[str, str]:
        return {}

    def hooks(self) -> List[JsonMerge]:
        return []

    def registered_mcp(self) -> Iterable[str]:
        """How the user's tool registered its MCP servers, e.g. 'user:codebase-memory-mcp'."""
        return []

    # ---- shared helpers ------------------------------------------------------------------------
    def marker(self, source: str) -> str:
        return f"<!-- {files.MARKER}: aos adapt-native {self.TOOL} desde {source} (+ .local.md). No editar -->"

    def skill_md(self, skill: sources.Skill) -> str:
        return "\n".join([
            "---", f"name: {skill.name}", f"description: {json.dumps(skill.description, ensure_ascii=False)}", "---",
            self.marker(f".aos/skills/specs/{skill.name}.md"), "", skill.body,
        ])

    def tool_version(self) -> str:
        exe = shutil.which(self.VERSION_COMMAND[0]) if self.VERSION_COMMAND else None
        if not exe:
            return "desconocida"
        try:
            out = subprocess.run([exe, *self.VERSION_COMMAND[1:]], capture_output=True, text=True, timeout=15,
                                 encoding="utf-8", errors="replace").stdout.split()
        except (OSError, subprocess.SubprocessError):
            return "desconocida"
        return out[0] if out else "desconocida"

    @staticmethod
    def load_json(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}

    def mcp_mapping(self) -> Dict[str, str]:
        registered = sorted(self.registered_mcp())
        mapping = {}
        for name in sources.mcp_servers(self.root):
            hit = next((r for r in registered if name in r.split(":", 1)[1]), None)
            if not hit:
                self.warnings.append(f"MCP `{name}` no está registrado en {self.TOOL}: instálalo a nivel de usuario (queda como convención)")
            mapping[name] = hit or "convention"
        return mapping

    def confined(self, rel: str) -> Optional[Path]:
        """Resolved path of `rel` if it stays inside the project (no '..', absolute paths or symlinks out)."""
        path = (self.root / rel).resolve()
        return path if self.root.resolve() in path.parents else None

    # ---- orchestration -------------------------------------------------------------------------
    def run(self, dry_run: bool = False, yes: bool = False) -> List[str]:
        """Generate everything; returns the changes made (empty = already up to date)."""
        validate_tools_allowed(self.root)  # same check as `aos sync`: never translate an unknown value silently
        changes: List[str] = []
        old = read_manifest(self.root, self.TOOL)

        wanted = {**self.agents(sources.roles(self.root)), **self.skills(sources.skills(self.root))}
        written = []
        for rel, text in sorted(wanted.items()):
            path = self.confined(rel)
            if path is None:
                self.warnings.append(f"OMITIDO, fuera del proyecto (¿symlink?): {rel}")
                continue
            if path.exists() and not files.is_generated(path):
                self.warnings.append(f"OMITIDO, archivo sin marcador (no se toca): {rel}")
                continue
            result = files.write_text(path, text, dry_run)
            if result:
                changes.append(f"{result}: {rel}")
            written.append(rel)

        # Generated files from the previous run that no longer apply. The manifest is a local, editable file:
        # only marked files inside the project are deleted, compared by resolved path (./x, x\y, case)
        keep = {self.confined(rel) for rel in written}
        for rel in old.get("files", []):
            if "#" in rel:
                continue
            path = self.confined(rel)
            if path is None or path in keep or not path.exists():
                continue
            if not files.is_generated(path):
                if path.suffix == ".json":
                    self.warnings.append(f"REVISAR: {rel} figura en el manifiesto anterior pero no tiene marcador; bórralo a mano si es de DASS-AOS")
                continue
            if not dry_run:
                path.unlink()
                if path.name == "SKILL.md" and not any(path.parent.iterdir()):
                    path.parent.rmdir()
            changes.append(f"borrado: {rel}")

        merged = []
        for m in self.hooks():
            entry = f"{m.path}#{m.label}"
            try:
                result = files.merge_json(self.root / m.path, m.keypath, m.value, m.owns, dry_run or not yes)
            except files.UnreadableJson:
                self.warnings.append(f"OMITIDO, JSON ilegible (no se toca): {m.path}")
                continue
            if result and not yes:
                self.warnings.append(f"PENDIENTE (requiere --yes): {entry} = {json.dumps(m.value, ensure_ascii=False)}")
                if entry in old.get("files", []):
                    merged.append(m)  # still holds our older hook: keep it in the manifest and ignored
                continue
            if result:
                changes.append(f"{result}: {entry}")
            merged.append(m)

        ignored = written + sorted({m.path for m in merged})
        result = files.gitignore_block(self.root, self.TOOL, ignored, dry_run)
        if result == "sin cierre":
            self.warnings.append(f"OMITIDO .gitignore: el bloque {self.TOOL} tiene marcador de inicio sin cierre; arréglalo a mano")
        elif result:
            changes.append(f"actualizado: .gitignore (bloque {self.TOOL})")

        manifest = {
            "tool": self.TOOL,
            "tool_version": self.tool_version(),
            "verified": self.VERIFIED,
            "files": sorted(written) + [f"{m.path}#{m.label}" for m in merged],
            "mcp": self.mcp_mapping(),
            "enforcement": self.ENFORCEMENT,
            "source_hash": native_source_hash(self.root),
        }
        if {k: v for k, v in old.items() if k != "generated_at"} != manifest:
            manifest["generated_at"] = dt.date.today().isoformat()
            if not dry_run:
                path = manifest_path(self.root, self.TOOL)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            changes.append(f"actualizado: .aos/native/{self.TOOL}.json")
        return changes
