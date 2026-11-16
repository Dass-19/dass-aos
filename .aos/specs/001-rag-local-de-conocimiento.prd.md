---
id: 202611160855
type: prd
status: approved
tags: [spec/prd, rag, memory, context]
created: 2026-11-16
---

# PRD: RAG local de conocimiento

> Para agentes y desarrolladores que usan DASS-AOS: permite recuperar de forma instantánea y contextual los *gotchas*, lecciones, ADRs, *specs* y contratos relevantes para la tarea en curso antes de empezar a modificar código.

## Problema
Hoy `aos refresh` (`dass_aos/memory.py`) entrega una lista fija y genérica al inicio de sesión: los 5 *gotchas* abiertos más graves, las últimas 3 filas de `LEDGER.md`, las *specs* abiertas y la siguiente tarea del plan activo.
- **Evidencia en el código actual**: `run_memory_refresh()` en `dass_aos/memory.py` no recibe ni consulta el tema de la tarea, ni indexa `.aos/decisions/`, `.aos/contracts/` o `.aos/plans/`.
- **Impacto**: cuando un proyecto acumula conocimiento en `.aos/`, el agente arranca sin el contexto específico del módulo o dominio que va a tocar (o tiene que leer múltiples archivos manualmente en turnos exploratorios), aumentando el riesgo de repetir trampas conocidas o ignorar contratos/ADRs aplicables.

## Usuario y contexto
- **Quién lo usa**: Agentes de codificación (Claude Code, Antigravity, Cursor, etc.) y desarrolladores que ejecutan `aos` desde la CLI o desde hooks de inicio/pre-tarea.
- **Cuándo y dónde**: Al iniciar una sesión o antes de iniciar una tarea/fase (`session-start`, `pre-task`), desde la raíz de cualquier proyecto con `.aos/`.
- **Qué hace hoy en su lugar**: Lee `aos refresh` (genérico) y busca archivos manualmente con `grep`/`rg` o lectura secuencial en `.aos/knowledge/`, `.aos/decisions/` y `.aos/contracts/`.

## Alcance
- **Dentro (v1)**:
  - Indexación local e incremental (por hash/`mtime`) del conocimiento `.aos/`: `knowledge/gotchas/`, `knowledge/lessons/LEDGER.md`, `decisions/`, `specs/`, `contracts/` (`http/`, `events/`, `schemas/`) y `plans/` (`active/`, `completed/`).
  - *Chunking* consciente de la estructura (secciones `##` en Markdown, filas en `LEDGER.md`, bloques en contratos) preservando metadatos (tipo de artefacto, ruta, título, `severity`, `status`, `tags`).
  - Almacenamiento en un único archivo SQLite local en `.aos/.cache/context.db` (excluido de Git) con búsqueda híbrida: similitud vectorial (`sqlite-vec`) + búsqueda léxica (`FTS5`/BM25).
  - Embeddings locales mediante extra opcional `pip install dass-aos[rag]` (modelo ONNX ligero sin PyTorch), con *fallback* automático a modo solo léxico (`FTS5`/BM25) cuando `[rag]` no está instalado.
  - Nuevo comando `aos context ["<query>"]` con filtros (`--kind`, `--limit`, `--reindex`, `--json`); si se omite `<query>`, deriva la consulta automáticamente de la siguiente tarea pendiente del plan activo.
  - Integración en `aos refresh` y en las plantillas/hooks (`session-start.md`, `pre-task.md`) para adjuntar o invocar el contexto relevante al arrancar una tarea.
- **Fuera de alcance (no-objetivos v1)**:
  - Indexar código fuente del repositorio (se mantiene `codebase-memory` para grafos y símbolos de código).
  - Bases vectoriales externas (Chroma, LanceDB, Qdrant) o APIs remotas de embeddings.
  - Nuevo servidor MCP propio de `dass-aos`.
  - Hooks bloqueantes en cada prompt del usuario (`UserPromptSubmit`).

## Criterios de aceptación (medibles)
- [ ] **CA-1 (Indexación y chunking de `.aos/`)**: Al ejecutar `aos context "<query>"` en un proyecto con archivos en `gotchas/`, `LEDGER.md`, `decisions/`, `specs/`, `contracts/` y `plans/`, se crea `.aos/.cache/context.db` con chunks estructurados y metadatos (`kind`, `path`, `title`, `status`, `severity`).
- [ ] **CA-2 (Indexación incremental)**: Una segunda ejecución de `aos context` sin cambios en `.aos/` no reindexa ni recalcula embeddings de archivos sin modificar (verificable mediante contador/diagnóstico o test unitario de `mtime`/hash); al modificar o añadir un archivo, solo se actualiza ese archivo.
- [ ] **CA-3 (Búsqueda híbrida con `[rag]` y fallback sin dependencias)**: Con `dass-aos[rag]` instalado (`fastembed` + `sqlite-vec`), la consulta combina ranking vectorial y `FTS5`; sin `[rag]` instalado, `aos context` sigue funcionando en modo léxico (`FTS5`/BM25) sin errores ni excepciones, indicando el modo usado.
- [ ] **CA-4 (Consulta automática desde plan activo)**: Al ejecutar `aos context` sin argumentos en un proyecto con un plan activo con tareas `- [ ]`, toma automáticamente el texto de la siguiente tarea pendiente como consulta y devuelve resultados relevantes; si no hay plan activo ni query, informa claramente sin fallar.
- [ ] **CA-5 (Integración en `aos refresh` y filtros)**: `aos context` soporta `--kind`, `--limit`, `--reindex` y `--json` (salida estructurada válida); `aos refresh` muestra el bloque de contexto relevante de la siguiente tarea (o la indicación cuando no aplica) manteniendo compatibilidad con la salida actual.
- [ ] **CA-6 (Higiene Git y tests)**: `.aos/.cache/` queda ignorado en `.gitignore` generado/actualizado por `aos init`/`aos update`; toda la suite existente + tests nuevos pasan con `aos verify`.

## Riesgos de producto
- **Ruido en el contexto**: Si los chunks son demasiado grandes o devuelven artefactos `resuelta`/`completed` por encima de trampas vigentes, el agente pierde foco. Mitigación: priorizar por metadatos (`status`, `severity`) y limitar por defecto (`--limit`).
- **Peso o fallo de instalación de dependencias ONNX en distintos SO**: Mitigación: mantener `[rag]` como extra opcional y garantizar que el modo `FTS5`/BM25 funciona 100% con la stdlib de Python.

## Preguntas abiertas
- Ninguna para v1 (alcance y stack aprobados por el usuario).

## Referencias
- **TRD**: `001-rag-local-de-conocimiento.trd.md` (siguiente paso)
- **Plan**: pendiente
