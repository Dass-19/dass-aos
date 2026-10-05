---
id: 202610051530
type: plan
status: completed
priority: high
tags: [plan/refactor, plan/meta]
created: 2026-10-05
---

# Plan: Refactor — portabilidad del motor y adaptación al proyecto

> Objetivo (Definition of Done): `pip install dass-aos` + `aos init` en un repo ajeno deja un `.aos/` completo, commits que no se rompen, comandos de verificación detectados según el stack, y agentes/skills genéricos actualizables con agregados por proyecto. Tests verdes, CLI sin cambios de flags.

## Contexto
- Motivación: hoy el motor solo funciona clonando este repo. Templates en la raíz (no empaquetados), `aos.py` asumido en proyectos destino, copias de agentes/skills congeladas tras el `init`.
- Archivos previstos: `dass_aos/constants.py`, `dass_aos/bootstrap.py`, `dass_aos/sync.py`, `dass_aos/plans.py`, `pyproject.toml`, `dass_aos/templates/**`, `tests/*`
- ADRs vinculados: ADR-002 (híbrido CLI + estado local). Nuevo ADR-003 en Fase 6.

## Fases

### Bloque A — Bloqueantes (sin esto no se puede usar en otro proyecto)
- [x] Fase 1: Baseline. Ejecutar `python aos.py verify` y anotar resultado. Agregar un test que haga `init` en un tmpdir y verifique que `.aos/agents/` y `.aos/skills/specs/` **no** estén vacíos (debe pasar hoy desde el repo; servirá de red al mover templates).
- [x] Fase 2: Mover templates al paquete. `git mv` de `agents/ skills/specs/ contracts/ hooks/*.md knowledge/ plans/templates/ security/ decisions/ADR-001-plantilla.md mcp-config.json ci/` → `dass_aos/templates/`. Añadir `TEMPLATES_DIR` en `constants.py` y reemplazar los usos de `ENGINE_ROOT / ...` en `bootstrap.py`, `sync.py` y `plans.py`. Declarar `package-data` en `pyproject.toml`.
- [x] Fase 3: Comprobar instalación real. `pip install .` (no editable) en un venv temporal → `aos init` en tmpdir → `.aos/` completo. Si falla, la Fase 2 no está cerrada.
- [x] Fase 4: Quitar la dependencia de `aos.py` en proyectos destino. Instrucciones generadas, hook de git y skill specs usan `aos <cmd>` (o `python -m dass_aos <cmd>`, añadiendo `__main__.py`). El git hook no debe abortar el commit si `aos` no está en PATH: avisar y salir 0.
- [x] Fase 5: Borrar `skills/bin/` (shims que duplican el CLI y rompen fuera del repo) y el stub `pre_commit.py` generado inline; dejar una sola versión del pre-commit. Usar `VERSION` en lugar de `"v0.4.0"` escrito a mano en `sync.py`.

### Bloque B — Adaptación al proyecto
- [x] Fase 6: ADR-003 "Base genérica del motor + agregados locales". Decidir: el motor es dueño de `agents/*.md` y `skills/specs/*.md`; el proyecto solo escribe `*.local.md`. Registrar alternativas descartadas (copiar una vez / editar la copia).
- [x] Fase 7: Implementar base + agregados locales. `aos sync` regenera `.aos/agents/<rol>.md` = template del motor + `.aos/agents/<rol>.local.md` si existe (igual para skills). Los generados llevan una cabecera "no editar, usa <rol>.local.md". Test: editar el template y el `.local.md` → `sync` refleja ambos.
- [x] Fase 8: Detección de stack en `init`. Detectar `pyproject.toml` / `package.json` / `go.mod` / `Cargo.toml` y rellenar `lint_command` / `test_command` en `config.json` solo si están vacíos. Una tabla de mapeos, sin plugins. Test por cada stack con archivos falsos en tmpdir.
- [x] Fase 9: Skills condicionales. Campo opcional `applies_when:` (lista de globs) en el frontmatter de las skill specs; `sync` lista solo las que aplican (sin campo = siempre). Poner globs en `db-migration-check`, `generate-client` y `api-smoke-test`.

### Bloque C — Limpieza y cierre
- [x] Fase 10: Unificar docs de la raíz (`00-INDEX`, `ARCHITECTURE`, `BOOTSTRAP`, `QUICKSTART`) en `README.md` + `docs/`. Actualizar rutas citadas tras la Fase 2.
- [x] Fase 11: Verificación completa: `python aos.py verify`, `python aos.py scan --dry-run`, repetir la Fase 3 de punta a punta, `aos sync` en este repo y revisar el diff de CLAUDE/AGENTS/GEMINI.md.
- [x] Fase 12: Cierre. Gotcha sobre empaquetado (`package-data`), mover el plan a `archive/`, subir la versión a 0.5.0.

### Fuera de alcance (evaluar después)
- Generar formatos nativos por herramienta (`.claude/agents/`, `.claude/skills/`, hooks reales de SessionStart) desde `.aos/`.
- Hacer cumplir `tools_allowed` de los agentes (hoy solo es documentación).

## Discovery Trail / Bloqueos
- 2026-10-05: Revisión inicial. `ENGINE_ROOT` = raíz del repo y `pyproject` solo empaqueta `dass_aos*` → con instalación no editable, `init` no copia templates. El git hook `python aos.py verify || exit 1` rompe los commits en proyectos sin `aos.py`. `skills/bin/*` resuelven `dass_aos` vía `parents[2]` → ImportError fuera de este repo.
- 2026-10-05 Fase 1: baseline `verify` OK (ruff limpio, 6 tests). Agregado `test_init_copies_all_templates` (conjunto completo de agents, skills/specs, plans/templates, hooks, knowledge) → 7 tests OK.
- 2026-10-05 Fases 2-5: templates en `dass_aos/templates/` con el mismo layout que `.aos/` → `init` es un solo `copy_missing()` (bootstrap 212 → ~100 líneas). `ci/` también va ahí (se copia a `.aos/ci/`). Borrado `mcp-config.json` raíz (lo genera `init`). `package-data` con `templates/**/*` (setuptools>=64).
- Fase 3 verificada: `pip install .` (no editable) en venv limpio → `aos init` en repo nuevo → `.aos/` completo desde site-packages, commit OK con el hook.
- Desvío Fase 5: solo se borraron los 3 shims (`bootstrap_project`, `memory_refresh`, `sync_agent_instructions`). `run_smoke_test.py` y `git_atomic_commit.py` se quedan: son skills reales, solo stdlib, y sus specs ahora apuntan a `.aos/skills/bin/`.
- Git hook: `.git/hooks/pre-commit` → `.aos/hooks/pre_commit.py` → `python -m dass_aos verify`; sale 0 si no hay python o dass-aos. Mensajes en ASCII (gotcha cp1252). Añadido `dass_aos/__main__.py`.
- Pendiente fuera del plan: el `.git/hooks/pre-commit` de este repo no se tocó (init no sobreescribe hooks existentes).
- 2026-10-05 Fase 6: ADR-003 en `.aos/decisions/ADR-003-base-motor-agregados-locales.md`.
- Fase 7: `sync_engine_docs()` en `sync.py` (lo llaman `aos sync` y `aos init`). Marcador `<!-- DASS-AOS-GENERATED` tras el frontmatter; `<rol>.local.md` se anexa como "Agregados del proyecto"; los `.local` no se listan como roles/skills. Un archivo sin marcador que difiere del template → OMITIDO con aviso (probado en este repo: las 3 specs viejas quedaron protegidas hasta refrescarlas).
- Fase 8: no hizo falta detección nueva: `verifier.detect_stack_commands()` ya existía en runtime. `init` ahora la vuelca a `config.json` (visible y editable). Añadido `go vet` para Go. `verify` salta (no falla) si el ejecutable del comando no está instalado, salvo `--strict` → evita que el pre-commit bloquee por un `ruff` ausente.
- Fase 9: `applies_when` (lista JSON en una línea) en `db-migration-check`, `generate-client`, `api-smoke-test`. `generate-client` sale de la lista fija de comandos CLI para que el filtro aplique. En este repo `db-migration-check` ya no se lista.
- Fix de compatibilidad: `write_text(newline=)` es 3.10+ y el proyecto declara 3.8 → `write_bytes`.
- Riesgo conocido: al actualizar desde 0.4.0, los agents/specs copiados con la versión vieja quedan OMITIDOS (no se distinguen de ediciones a mano). Evaluar `aos sync --reset-engine-docs` si molesta.
- Tests: 14 OK (nuevos: agregados locales, propagación del motor, protección de editados, skill condicional, detección de stack).
- 2026-10-05 Fase 10: `00-INDEX`, `BOOTSTRAP` y `QUICKSTART` eliminados (contenido absorbido por `README.md`, que gana la sección "Adaptar DASS-AOS al Proyecto"). `ARCHITECTURE.md` → `docs/ARCHITECTURE.md` con sección de ADR-003. Corregidas referencias a `00-INDEX.md` en `hooks/session-start.md` y a `decisions/` del motor en ADR-001.
- Fase 11: verify (15 tests) y scan dry-run OK. Instalación limpia 0.5.0 repetida: stack Node detectado (`npm test`), `db-migration-check` listada al existir `migrations/`, `.local.md` anexado, commit con hook OK. Encontrado y corregido bug previo: cada `sync` añadía una línea en blanco tras el bloque gestionado (en este repo había 5). Test de idempotencia añadido.
- Fase 12: gotcha `templates-fuera-del-paquete.md`. Versión 0.5.0 (`constants.VERSION` es la única fuente; `cli` y `__init__` la importan; `pyproject` a mano).
- Limpieza: `pip install` desde el repo deja `build/` (ignorado por git), borrado.
