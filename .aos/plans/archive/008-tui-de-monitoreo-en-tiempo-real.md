---
id: 202611161043
type: plan
status: completed
priority: medium
tags: [plan/feature, tui, observability]
created: 2026-11-16
prd: 002-tui-de-monitoreo-en-tiempo-real.prd.md
trd: 002-tui-de-monitoreo-en-tiempo-real.trd.md
---

# Plan: Feature — TUI de monitoreo en tiempo real

> Objetivo (Definition of Done): Implementar y verificar `aos tui` con monitoreo en tiempo real de `.aos/`, Git, sesiones/tareas de Claude Code y Antigravity, buscador `aos context` y ejecución asíncrona de gates según `.aos/specs/002-tui-de-monitoreo-en-tiempo-real.prd.md` (`CA-1`..`CA-7`) y `.aos/specs/002-tui-de-monitoreo-en-tiempo-real.trd.md`.

## Contexto y Archivos Afectados
- PRD: `.aos/specs/002-tui-de-monitoreo-en-tiempo-real.prd.md` (criterios de aceptación: `CA-1`..`CA-7`)
- TRD: `.aos/specs/002-tui-de-monitoreo-en-tiempo-real.trd.md`
- Archivos previstos:
  - `pyproject.toml` (extra `[tui]`, `package-data` para `*.tcss`)
  - `dass_aos/telemetry.py` (nuevo — motor de snapshot y eventos delta en stdlib)
  - `dass_aos/tui/__init__.py` (nuevo — entrypoint con guard de importación perezosa)
  - `dass_aos/tui/app.py` (nuevo — aplicación Textual, workers y navegación)
  - `dass_aos/tui/widgets.py` (nuevo — paneles y vistas por dominio)
  - `dass_aos/tui/styles.tcss` (nuevo — estilos Textual)
  - `dass_aos/cli.py` (subcomando `aos tui`)
  - `README.md` (documentación de `aos tui` y extra `[tui]`)
  - `tests/test_telemetry.py` (nuevo)
  - `tests/test_tui.py` (nuevo)
- ADRs vinculados: `ADR-010-tui-opcional-textual-y-telemetria-local.md`
- Gotchas a considerar: `windows-cp1252-encoding.md`, `templates-fuera-del-paquete.md`
- Contratos a crear/actualizar: estructuras de datos internas en `.aos/specs/002-tui-de-monitoreo-en-tiempo-real.trd.md` §Contratos
- Riesgo (ADR-008): medio (nueva dependencia opcional `[tui]`, concurrencia en workers de refresco/subprocesos y lectura de JSONL en escritura en Windows/Linux) — revisión de 1 lente al cierre.

> La spec se cita, nunca se parafrasea: los handoffs apuntan a la ruta y a la sección del PRD/TRD.

## Fases de Ejecución Atómica
> Cada fase termina con su línea `Gate:` (comando exacto y resultado esperado). Una fase no empieza hasta que la anterior la pasa. Flujo completo en la skill `phased-delivery`. El tamaño de la tarea se decide por riesgo y comprensión, no por número de archivos (ADR-008).

- [x] Fase 1: Discovery & requisitos
  - Línea base: `python -m dass_aos verify` en verde (`ruff check .` PASSED, `124` unit tests OK)
  - Decisiones registradas en el Discovery Trail
  - PRD `002-tui-de-monitoreo-en-tiempo-real.prd.md` (`CA-1`..`CA-7`) y TRD `002-tui-de-monitoreo-en-tiempo-real.trd.md` redactados
  - Gate: PRD con criterios medibles y TRD que cita el PRD
- [x] Fase 2: Diseño
  - `ADR-010-tui-opcional-textual-y-telemetria-local.md` creado para el extra opcional `[tui]` y límites de telemetría
  - Aprobado por el usuario (con énfasis en diseño visual cuidado y limpio)
  - Gate: plan aprobado por el usuario
- [x] Fase 3: Implementación (en orden de dependencias)
  - 3.1: `pyproject.toml` (extra `tui` y `package-data` `tui/*.tcss`) + `dass_aos/telemetry.py` (snapshot `.aos/`, Git, parsers Claude Code y Antigravity, `diff_snapshots`) + `tests/test_telemetry.py` (RED → GREEN)
  - 3.2: `dass_aos/tui/` (`__init__.py`, `styles.tcss`, `widgets.py`, `app.py` con las 6 vistas, refresco en worker, buscador `aos context` y runner de `verify`/`scan`/`sync`/`refresh`) + `dass_aos/cli.py` (`aos tui`) + `tests/test_tui.py`
  - 3.3: Documentación en `README.md` (sección CLI y dependencias opcionales `[tui]`)
  - Gate: `python -m dass_aos verify` en verde (`ruff check .` PASSED + `131` tests OK)
- [x] Fase 4: Verificación en vivo (`live-verify`)
  - Extra `[tui]` (`textual-8.2.8`) instalado y ejercitado contra `dass-aos` en `140x42` y `96x30`
  - Corregidos en ronda 1-3: colisión de claves en `agents-tasks-table` (`task-14.log` entre conversaciones), título limpio de `<USER_REQUEST>`, rebote de `TabbedContent.active` al perder foco un botón (`set_focus(None)`), `auto_scroll=False` en logs superiores
  - Gate: `LIVE VERIFY OK` en `140x42` y `96x30` con capturas SVG inspeccionadas
- [x] Fase 5: Revisión con recibo (`adversarial-review`, ADR-008, riesgo medio: 1 lente)
  - Candidato congelado `f21037384b9d916493b994a8d26b89174329a444` antes de revisar; revisado con 1 lente (`Resilience`)
  - Gate: recibo y acuse anotados; test RED→GREEN para `updatedAt` ISO-8601 y `8/8` tests en `test_telemetry.py` + `test_tui.py` + `LIVE VERIFY OK`
- [x] Fase 6: Cierre
  - `python -m dass_aos verify`, `python -m dass_aos scan --dry-run` y `python -m dass_aos doctor` en verde; lección anotada en `.aos/knowledge/lessons/LEDGER.md` y plan archivado en `.aos/plans/archive/`

## Registro de Preguntas y Decisiones (Discovery Trail)
- **Pregunta 1:** ¿Qué alcance quieres para la TUI (`aos tui`) en esta primera versión?
  - **Opciones:** Monitor completo `.aos/` + Git + acciones / Monitor completo + feed de sesiones del agente / Solo monitor pasivo read-only.
  - **Decisión:** Monitor completo de todo DASS-AOS + sesiones/agentes de Claude Code y Antigravity + tasks en background + planes + acciones rápidas en vivo.
- **Pregunta 2:** ¿Qué arquitectura de dependencias prefieres para la TUI?
  - **Opciones:** Extra opcional `[tui]` con `textual` / Extra opcional `[tui]` con `rich` / Solo stdlib ANSI.
  - **Decisión:** Extra opcional `[tui]` con `textual` (mantiene el núcleo sin dependencias obligatorias; requiere `pip install "dass-aos[tui]"`).
- **Pregunta 3:** ¿Cómo prefieres avanzar?
  - **Opciones:** Primero crear PRD, TRD, ADR y plan para aprobar antes de implementar / Seguir de corrido tras crear docs.
  - **Decisión:** Primero crear PRD, TRD, ADR y plan y presentarlos para aprobación antes de escribir código.
- **Fecha:** 2026-11-16

## Registro de Bloqueos
- Ninguno (aprobado para implementar Fase 3).

## Recibo de Revisión (RDD)
- Candidato: `f21037384b9d916493b994a8d26b89174329a444` · 11 archivos/rutas (`README.md`, `dass_aos/cli.py`, `pyproject.toml`, `dass_aos/telemetry.py`, `dass_aos/tui/*`, `tests/test_telemetry.py`, `tests/test_tui.py`, specs/ADR/plan) · 2026-11-16 11:03
- Tier: medio (UI con estado, workers en segundo plano y parsing local de JSONL sin contrato externo compartido)
- Lentes: 1 (`Resilience: concurrencia, compatibilidad Python 3.8 / Windows y degradación sin [tui]`)

### Acuse
- Candidato revisado: `f21037384b9d916493b994a8d26b89174329a444` · tier medio · 1 lente (`Resilience`)
- Confirmados: 3
  1. `high` · `dass_aos/telemetry.py:449` — `float(updated_raw)` lanzaba `ValueError` no capturado si una sesión de Claude Code usaba timestamp ISO-8601 o no numérico (abortaba todo `collect_telemetry`).
  2. `medium` · `dass_aos/tui/app.py:756` — `_refresh_worker()` se invocaba desde el hilo secundario de `_run_aos_worker` en lugar del loop principal de Textual.
  3. `medium` · `dass_aos/tui/app.py:707,740` — mutación de `_runner_jobs`/`tail_lines` desde el worker y falta de `terminate()` sobre `_active_proc` en `on_unmount()`.
- Refutados: 1 (compatibilidad Python 3.8 en `telemetry.py` / `tui/__init__.py` revisada sin sintaxis/APIs incompatibles)
- Corrección: añadido `_parse_timestamp()` compatible Python >=3.8 (`telemetry.py`), movidas mutaciones de `_runner_jobs`/`tail_lines` y `_refresh_worker()` al hilo UI y añadido `on_unmount()` (`app.py`) · gates repetidos: `test_telemetry.py` + `test_tui.py` (`8/8 OK`) + `live_verify_tui.py` (`LIVE VERIFY OK`) + `aos verify` → verde
- Pendientes: 0
- Documentos corregidos: `.aos/knowledge/lessons/LEDGER.md` (fila sobre `set_focus(None)` en `TabbedContent`)
