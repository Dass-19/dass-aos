---
id: 202611160856
type: plan
status: active
priority: medium
tags: [plan/feature, rag, memory]
created: 2026-11-16
prd: 001-rag-local-de-conocimiento.prd.md
trd: 001-rag-local-de-conocimiento.trd.md
---

# Plan: Feature — RAG local de conocimiento

> Objetivo (Definition of Done): Implementar y verificar el RAG local de conocimiento `.aos/` según `001-rag-local-de-conocimiento.prd.md` (`CA-1`..`CA-6`) y `001-rag-local-de-conocimiento.trd.md`.

## Contexto y Archivos Afectados
- PRD: `.aos/specs/001-rag-local-de-conocimiento.prd.md` (criterios de aceptación: `CA-1`..`CA-6`)
- TRD: `.aos/specs/001-rag-local-de-conocimiento.trd.md`
- Archivos previstos:
  - `dass_aos/rag.py` (nuevo)
  - `dass_aos/cli.py`
  - `dass_aos/memory.py`
  - `dass_aos/bootstrap.py`
  - `dass_aos/update.py`
  - `dass_aos/templates/hooks/session-start.md`
  - `dass_aos/templates/hooks/pre-task.md`
  - `pyproject.toml`
  - `tests/test_rag.py` (nuevo)
- ADRs vinculados: `[ADR-009-rag-local-conocimiento-sqlite-fastembed.md]`
- Gotchas a considerar: []
- Contratos a crear/actualizar: esquema JSON CLI en `001-rag-local-de-conocimiento.trd.md` §Contratos
- Riesgo: medio (nueva dependencia opcional `[rag]`, persistencia local SQLite, compatibilidad Python >=3.8 sin `[rag]`) — revisión de 1 lente al cierre.

> La spec se cita, nunca se parafrasea: los handoffs apuntan a la ruta y a la sección del PRD/TRD.

## Fases de Ejecución Atómica
- [x] Fase 1: Discovery & requisitos
  - Línea base: `ruff check .` + `117` tests en verde (`3b2301c`)
  - Decisiones registradas en Discovery Trail
  - PRD `001-rag-local-de-conocimiento.prd.md` y TRD `001-rag-local-de-conocimiento.trd.md` creados
  - Gate: PRD con CA-1..CA-6 medibles y TRD enlazado
- [x] Fase 2: Diseño
  - `ADR-009-rag-local-conocimiento-sqlite-fastembed.md` creado para el extra opcional `[rag]` y `.aos/.cache/context.db`
  - Gate: diseño y plan listos para implementación
- [x] Fase 3: Implementación (por capas, en orden de dependencias)
  - 3.1: `pyproject.toml` (`[project.optional-dependencies] rag`) + `.gitignore` (`.aos/.cache/`) en `dass_aos/sync.py`
  - 3.2: `dass_aos/rag.py` (chunker, indexador incremental, SQLite FTS5 + `sqlite-vec` + `fastembed` opcional con fallback léxico, ranking híbrido RRF) + `tests/test_rag.py`
  - 3.3: `dass_aos/cli.py` (`aos context`) + `dass_aos/memory.py` (`run_memory_refresh` con contexto relevante de la siguiente tarea) + plantillas `session-start.md` / `pre-task.md` + `README.md`
  - Gate: `python -m dass_aos verify` en verde
- [x] Fase 4: Verificación en vivo (`live-verify`)
  - Ejecutado `python -m dass_aos sync` y `python -m dass_aos context "rag" --json`: 22 archivos indexados en `.aos/.cache/context.db` (modo `lexical`), resultados ordenados con score y snippet
  - Gate: evidencia verificada en salida JSON y `.gitignore` actualizado
- [x] Fase 5: Revisión con recibo (`adversarial-review`, riesgo medio: 1 lente)
  - Revisión de compatibilidad Python >=3.8, degradación limpia sin `[rag]`, escape seguro de `FTS5` y preservación de `.gitignore`
  - Gate: `test_native.py` actualizado para `.aos/.cache/` y suite completa en verde
- [x] Fase 6: Cierre en `dass-aos`
  - `python -m dass_aos verify` + `python -m dass_aos scan --dry-run` + `aos adapt-native antigravity --yes`
- [ ] Fase 7: Actualización en proyectos existentes
  - **Pendiente de confirmación del usuario**: preguntar cuáles proyectos y en qué ramas antes de ejecutar `aos update` / `aos context --reindex`

## Registro de Preguntas y Decisiones (Discovery Trail)
- **Pregunta 1:** ¿Qué fuentes debe indexar el RAG local en la v1?
  - **Decisión:** Solo conocimiento `.aos/` (`gotchas`, `lessons`, `decisions`, `specs`, `contracts`, `plans`); el código sigue usando `codebase-memory`.
- **Pregunta 2:** ¿Cómo generar los embeddings locales?
  - **Decisión:** Extra opcional `[rag]` con modelo local ligero (`fastembed` / ONNX, sin PyTorch) + fallback léxico si no está instalado.
- **Pregunta 3:** ¿Qué base vectorial local usar?
  - **Decisión:** SQLite local en `.aos/.cache/context.db` (`sqlite-vec` + `FTS5` híbrido en un solo archivo).
- **Pregunta 4:** ¿Cómo recibe el agente el contexto recuperado?
  - **Decisión:** Comando explícito `aos context "<query>"` (o automático desde la siguiente tarea del plan activo) + integración en `aos refresh`.
- **Fecha:** 2026-11-16

## Registro de Bloqueos
-
