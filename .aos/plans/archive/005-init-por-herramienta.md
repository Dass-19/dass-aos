---
id: 202610161900
type: plan
status: done
priority: medium
tags: [plan/feature]
created: 2026-10-16
---

# Plan: Feature — `aos init` por herramienta

> Objetivo (Definition of Done):
> - `aos init <herramienta>...` crea solo el archivo de instrucciones de cada herramienta elegida y la guarda en `.aos/config.json` (`"tools"`).
> - `aos sync` respeta esa elección: crea solo esos archivos y sigue actualizando los que ya existan.
> - Sin argumento, `aos init` usa las herramientas configuradas o las que detecta en el repo; si no hay ninguna, falla sin escribir nada.
> - Para las herramientas con generador, `init` genera sus nativos sin hooks.

## Contexto y Archivos Afectados
- **Origen:** petición del usuario. `init` creaba siempre `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules` y `.windsurfrules`, aunque solo se use una herramienta (p. ej. Antigravity).
- **Archivos:**
  - `dass_aos/constants.py` (`TOOL_FILES`, `TOOL_SIGNS`)
  - `dass_aos/sync.py` (`configured_tools`, `detect_tools`, `sync_all_instructions`)
  - `dass_aos/bootstrap.py` (`resolve_tools`, `init_project(tools, native)`)
  - `dass_aos/cli.py`
  - `tests/test_init.py`, `tests/test_sync.py` y los `init_project` del resto de tests
  - `README.md`, `templates/skills/specs/bootstrap-project.md`
- **ADRs vinculados:** ADR-005, porque `init` invoca el generador.

## Fases de Ejecución Atómica
- [x] Fase 1: Mapa herramienta → archivo y detección.
  - `claude-code` → `CLAUDE.md`
  - `antigravity`, `gemini-cli` → `GEMINI.md`
  - `codex`, `opencode` → `AGENTS.md`
  - `cursor` → `.cursorrules`
  - `windsurf` → `.windsurfrules`
  - La detección se basa en las carpetas y archivos propios de cada herramienta.
  - Gate: tests.
- [x] Fase 2: `init` y `sync`.
  - `resolve_tools` se ejecuta antes de escribir nada (nuestros archivos parecerían señales de herramientas).
  - Las herramientas se acumulan en `config.json`.
  - `sync` deja de tener `--create-missing`, que siempre valía `True` y no se podía desactivar.
  - Gate: `aos verify`, 63 tests.
- [x] Fase 3: `init` genera los nativos (decisión del usuario: sí, sin hooks) e indica cómo aplicar los hooks pendientes.
  - Gate: `live-verify` por la vía CLI en un venv limpio:
    - repo vacío → error y nada escrito;
    - `init antigravity` → solo `GEMINI.md` + `.agents/` + hook PENDIENTE;
    - `init claude-code` más tarde → solo `CLAUDE.md` + `.claude/`;
    - `sync` → SIN CAMBIOS.
- [x] Fase 4: `adversarial-review` (lente de correctitud y compatibilidad), README y skill `bootstrap-project`, cierre.

## Registro de Preguntas y Decisiones (Discovery Trail)
- 2026-10-16 · Sin argumento: detectar las herramientas y, si no hay ninguna, pedirla (sin escribir nada). Decisión del usuario.
- 2026-10-16 · `init <tool>` ejecuta también `adapt-native <tool>` sin `--yes`: subagentes y skills sí; hooks pendientes de revisión. Decisión del usuario.
- 2026-10-16 · Los archivos de herramientas no configuradas que ya existen no se borran; `sync` los sigue actualizando. Quitarlos lo decide el usuario.

- 2026-10-16 · `adversarial-review`, lente de correctitud y compatibilidad: 6 hallazgos, los 6 confirmados por `adversarial-verifier` y corregidos con test.
  - I1: en proyectos anteriores a 0.6.0 se tomaban como señal los archivos escritos por DASS-AOS → ya no cuentan si llevan el bloque gestionado.
  - I2: `.agents/` daba un falso Antigravity (`.agents/skills/` es el estándar compartido) → señales propias según su documentación local (`hooks.json`, `skills.json`, `plugins.json`, `plugins/`, `rules/`, `.agent`, `_agents`, `_agent`).
  - I3, I4 e I5: un `config.json` inválido, con `"tools"` que no es lista o con herramientas desconocidas → error que nombra el archivo, antes de escribir nada.
  - I6: un rol del proyecto roto ya no impide instalar el pre-commit; el error nombra el archivo, y el estado de los nativos se informa después de generarlos.
- 2026-10-16 · Cierre: `aos verify` (68 tests) y `aos scan --dry-run` OK. Este repo declara `claude-code` y `antigravity`; sus `AGENTS.md`, `.cursorrules` y `.windsurfrules` anteriores se conservan, y borrarlos lo decide el usuario.

## Registro de Bloqueos
-
