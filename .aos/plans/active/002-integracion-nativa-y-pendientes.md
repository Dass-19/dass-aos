---
id: 202610051730
type: plan
status: active
priority: medium
tags: [plan/feature, plan/meta]
created: 2026-10-05
---

# Plan: Feature — integración nativa por herramienta y pendientes de 0.5.0

> Objetivo (Definition of Done): `aos sync` genera, desde `.aos/` como única fuente, los formatos nativos de Claude Code (subagentes, skills, hook de SessionStart) con `tools_allowed` aplicado de verdad donde la herramienta lo soporta; los pendientes de 0.5.0 quedan resueltos. Tests verdes, `.aos/` sigue siendo la fuente de verdad (ADR-002/003).

## Contexto
- Origen: pendientes del plan archivado `001-portabilidad-y-adaptacion.md`.
- Hoy `hooks/*.md` y `tools_allowed` son solo texto: el agente tiene que "acordarse" de ejecutar `aos refresh` y nada limita sus herramientas.
- Archivos previstos: `dass_aos/sync.py` (o `dass_aos/native.py` si crece), `dass_aos/cli.py`, `dass_aos/templates/agents/*.md`, `dass_aos/templates/skills/specs/*.md`, `tests/`
- ADRs vinculados: ADR-002, ADR-003. Nuevo ADR-004 en Fase 3.
- Fuera de alcance: `LICENSE` (lo agrega el autor).

## Fases

### Bloque A — Pendientes de 0.5.0
- [ ] Fase 1: Reemplazar `.git/hooks/pre-commit` de este repo (todavía `python aos.py verify || exit 1`) por el hook nuevo que delega en `.aos/hooks/pre_commit.py`. Agregar `aos init --force-hooks` (o similar) solo si se ve necesario; si no, documentar el reemplazo manual en el README.
- [ ] Fase 2: `aos sync --reset-engine-docs`: regenera agents/skill specs del motor aunque no tengan marcador, guardando antes el archivo previo como `<nombre>.local.md.bak` (nunca perder contenido). Resuelve la migración desde 0.4.0. Test: archivo sin marcador → reset → generado + `.bak` con el contenido original.

### Bloque B — Formatos nativos (Claude Code primero)
- [ ] Fase 3: Investigación + ADR-004. Confirmar contra la documentación actual de Claude Code (context7 / claude-code-guide) el formato de: subagentes `.claude/agents/<nombre>.md` (frontmatter `name`, `description`, `tools`), skills `.claude/skills/<nombre>/SKILL.md` (frontmatter `name`, `description`), y hooks en `.claude/settings.json` (`SessionStart` → `aos refresh`). Decidir en ADR-004: los nativos son **artefactos generados** (marcador + regenerados por `sync`, nunca editados a mano), qué herramientas se cubren (Claude Code ahora; Gemini/Cursor/Codex evaluados y anotados) y si se commitean o se ignoran en git.
- [ ] Fase 4: Metadatos necesarios en los templates. Los roles no tienen `description` usable para que la herramienta decida cuándo delegar: añadir `description:` en el frontmatter de cada `agents/*.md` (derivado de "Misión"/"Cuándo asumirlo"). Verificar que todas las skill specs tienen `name` y una descripción de una línea.
- [ ] Fase 5: Generar `.claude/agents/<rol>.md` desde `.aos/agents/<rol>.md` ya renderizado (base + `.local.md`): frontmatter nativo + cuerpo del rol. Respetar el marcador de generado; no tocar subagentes del usuario que no tengan marcador. Test con tmpdir.
- [ ] Fase 6: Generar `.claude/skills/<skill>/SKILL.md` desde `.aos/skills/specs/` respetando `applies_when` (si no aplica, no se genera; si dejó de aplicar y es generado, se borra). Test: crear/quitar `migrations/` → aparece/desaparece `db-migration-check`.
- [ ] Fase 7: Hook real de SessionStart: fusionar en `.claude/settings.json` una entrada `SessionStart` que ejecute `aos refresh` **sin pisar** otros hooks ni settings del usuario (merge de JSON, idempotente, identificable para poder actualizarla). Test: settings con hooks previos → sync dos veces → una sola entrada DASS-AOS, previas intactas.

### Bloque C — Hacer cumplir `tools_allowed`
- [ ] Fase 8: Vocabulario. Hoy `tools_allowed` mezcla nombres inventados (`read_file`, `git_diff`) con skills (`semgrep-scan`). Definir un vocabulario neutral y pequeño (p. ej. `read`, `search`, `edit`, `write`, `shell:<cmd>`, `skill:<nombre>`) y una tabla de mapeo por herramienta (Claude Code: `Read`, `Grep`, `Glob`, `Edit`, `Write`, `Bash(aos scan:*)`…). Registrar en ADR-004. Migrar los 6 roles.
- [ ] Fase 9: Aplicar el mapeo en el `tools:` de `.claude/agents/<rol>.md` (enforcement real en Claude Code). Un valor desconocido en `tools_allowed` hace fallar `sync` con mensaje claro (no se ignora en silencio). Test: rol `reviewer` sin `edit`/`write` → su subagente no los lista.
- [ ] Fase 10: Herramientas sin enforcement nativo (Cursor, Windsurf, Gemini, AGENTS.md): dejar la restricción como texto explícito en el bloque gestionado y documentar en el README que ahí es solo una convención.

### Bloque D — Cierre
- [ ] Fase 11: Verificación completa: `aos verify`, `aos scan --dry-run`, instalación limpia (`pip install .` no editable en venv) → `aos init` → abrir Claude Code en el proyecto y comprobar que el SessionStart ejecuta `aos refresh` y que los subagentes aparecen con sus herramientas limitadas.
- [ ] Fase 12: README (sección de integración nativa y tabla de qué se aplica en cada herramienta), gotchas nuevos si aparecen, archivar el plan, versión 0.6.0.

## Discovery Trail / Bloqueos
- 2026-10-05: Plan creado a partir de los pendientes del plan 001. Riesgo principal: los formatos nativos cambian con las versiones de cada herramienta → por eso la Fase 3 verifica contra la documentación actual antes de escribir código, y todo lo nativo es generado y regenerable.
