"""Plan management module for creating and archiving task plans."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from .constants import AOS_DIR_NAME, TEMPLATES_DIR, configure_utf8_output
from .ui import Card, bold, cyan, dim, green


def slugify(value: str) -> str:
    """Normalize string to URL-safe slug."""
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-")


def create_new_plan(
    project_root: Path,
    template_type: str = "feature",
    title: str = "new-task",
) -> Path:
    """Create a new active plan from template."""
    configure_utf8_output()
    project_root = project_root.resolve()

    # Search for template in .aos/plans/templates or the packaged templates
    template_paths = [
        project_root / AOS_DIR_NAME / "plans" / "templates" / f"{template_type}.md",
        TEMPLATES_DIR / "plans" / "templates" / f"{template_type}.md",
    ]
    template_file = next((p for p in template_paths if p.exists()), None)

    if not template_file:
        raise FileNotFoundError(f"Template '{template_type}' not found in templates directory.")

    content = template_file.read_text(encoding="utf-8")

    now = dt.datetime.now()
    plan_id = now.strftime("%Y%m%d%H%M")
    date_str = now.strftime("%Y-%m-%d")

    # Replace placeholders
    content = content.replace("{{YYYYMMDDHHmm}}", plan_id)
    content = content.replace("{{YYYY-MM-DD}}", date_str)
    content = content.replace("{{SHORT_TITLE}}", title)
    content = content.replace("{{MEASURABLE_CRITERIA}}", f"Implement and verify {title}")

    # Determine next plan index in active/
    active_dir = project_root / AOS_DIR_NAME / "plans" / "active"
    active_dir.mkdir(parents=True, exist_ok=True)

    # Highest NNN- prefix across active/ and archive/: counting files reuses numbers once plans are archived
    numbers = [int(m[1]) for p in active_dir.parent.glob("*/*.md") if (m := re.match(r"(\d+)-", p.name))]
    next_index = max(numbers, default=0) + 1
    slug = slugify(title)
    target_filename = f"{next_index:03d}-{slug}.md"
    target_path = active_dir / target_filename

    target_path.write_text(content, encoding="utf-8")

    card = Card("Nuevo Plan", target_filename)
    card.field("Plantilla", bold(template_type))
    card.field("Título", title)
    card.field("Archivo", dim(str(target_path)))
    card.empty()
    card.line(f"  {green('✓')} Plan activo creado en {bold('.aos/plans/active/' + target_filename)}")
    card.line(f"  {cyan('▶')} {dim('Siguiente paso:')} Completa la Fase 1 (Discovery & contratos) y revisa con {bold('aos status')}")
    print(card.render())

    return target_path
