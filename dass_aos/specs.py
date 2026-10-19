"""PRD/TRD spec management (ADR-007).

A spec is the requirement that outlives the plan: the PRD says what problem we solve
and how we know it worked; the TRD says how we build it. Both share the NNN index of
the feature, like the NNN-<slug>.design.md of `phased-delivery`.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import List, NamedTuple, Optional

from .constants import AOS_DIR_NAME, TEMPLATES_DIR, configure_utf8_output
from .plans import slugify

SPEC_KINDS = ("prd", "trd")
CLOSED_STATUSES = {"closed", "archived", "cerrado", "archivado", "done"}
_SPEC_NAME = re.compile(r"^(\d+)-(.+)\.(prd|trd)\.md$")


class SpecInfo(NamedTuple):
    """One spec file as `aos refresh` and `aos doctor` need to see it."""

    index: int
    slug: str
    kind: str
    path: Path
    title: str
    status: str

    @property
    def has_counterpart(self) -> bool:
        other = "trd" if self.kind == "prd" else "prd"
        return self.path.with_name(f"{self.index:03d}-{self.slug}.{other}.md").exists()


def specs_dir(project_root: Path) -> Path:
    return project_root / AOS_DIR_NAME / "specs"


def read_frontmatter(path: Path) -> dict:
    """Minimal YAML frontmatter reader: `key: value` lines only (no dependencies)."""
    data: dict = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return data
    if not text.startswith("---"):
        return data
    end = text.find("\n---", 3)
    if end == -1:
        return data
    for line in text[3:end].splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip().strip("\"'")
    return data


def read_specs(project_root: Path) -> List[SpecInfo]:
    """All spec files, ordered by index; unreadable ones are skipped rather than raising."""
    directory = specs_dir(project_root)
    if not directory.exists():
        return []
    specs: List[SpecInfo] = []
    for path in directory.glob("*.md"):
        match = _SPEC_NAME.match(path.name)
        if not match:
            continue
        meta = read_frontmatter(path)
        title = ""
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
        except OSError:
            pass
        specs.append(
            SpecInfo(
                index=int(match.group(1)),
                slug=match.group(2),
                kind=match.group(3),
                path=path,
                title=title or match.group(2),
                status=(meta.get("status") or "draft").lower(),
            )
        )
    return sorted(specs, key=lambda s: (s.index, s.kind, s.slug))


def open_specs(project_root: Path, limit: int = 5) -> List[SpecInfo]:
    """Specs still open; closed/archived ones are left out of the session-start digest."""
    return [s for s in read_specs(project_root) if s.status not in CLOSED_STATUSES][:limit]


def _next_index(directory: Path) -> int:
    numbers = [int(m.group(1)) for p in directory.glob("*.md") if (m := _SPEC_NAME.match(p.name))]
    return max(numbers, default=0) + 1


def _index_for_slug(directory: Path, slug: str) -> Optional[int]:
    """The NNN already used by this feature, so its TRD lands next to its PRD."""
    for path in directory.glob("*.md"):
        match = _SPEC_NAME.match(path.name)
        if match and match.group(2) == slug:
            return int(match.group(1))
    return None


def create_new_spec(
    project_root: Path,
    kind: str = "prd",
    title: str = "new-spec",
) -> Path:
    """Create `.aos/specs/NNN-<slug>.<kind>.md` from the packaged template."""
    configure_utf8_output()
    project_root = project_root.resolve()

    if kind not in SPEC_KINDS:
        raise ValueError(f"tipo de especificación desconocido: {kind}. Disponibles: {', '.join(SPEC_KINDS)}")

    template = TEMPLATES_DIR / "specs" / "templates" / f"{kind}.md"
    if not template.exists():
        raise FileNotFoundError(f"Plantilla '{kind}' no encontrada en {template.parent}.")

    directory = specs_dir(project_root)
    directory.mkdir(parents=True, exist_ok=True)

    now = dt.datetime.now()
    content = template.read_text(encoding="utf-8")
    content = content.replace("{{YYYYMMDDHHmm}}", now.strftime("%Y%m%d%H%M"))
    content = content.replace("{{YYYY-MM-DD}}", now.strftime("%Y-%m-%d"))
    content = content.replace("{{SHORT_TITLE}}", title)

    slug = slugify(title)
    index = _index_for_slug(directory, slug) or _next_index(directory)
    target = directory / f"{index:03d}-{slug}.{kind}.md"
    if target.exists():
        pair = "prd" if kind == "trd" else "trd"
        raise FileExistsError(
            f"ya existe {target.name}; usa otro título o edita el archivo. "
            f"La pareja de esta funcionalidad sería {index:03d}-{slug}.{pair}.md"
        )

    target.write_text(content, encoding="utf-8")
    print(f"[spec] CREATED new {kind.upper()}: {target}")
    return target
