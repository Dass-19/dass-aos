---
id: 202611160855
type: trd
status: approved
tags: [spec/trd, rag, sqlite, fastembed]
created: 2026-11-16
prd: 001-rag-local-de-conocimiento.prd.md
---

# TRD: RAG local de conocimiento

> Cómo se construye y por qué así. **No repite el PRD: lo cita.**

## Contexto
- **PRD**: `001-rag-local-de-conocimiento.prd.md` — cubre `CA-1`, `CA-2`, `CA-3`, `CA-4`, `CA-5`, `CA-6`.
- **Componentes previstos**:
  - `dass_aos/rag.py` (nuevo): chunker estructurado, indexador incremental, backend SQLite (`FTS5` + `sqlite-vec` opcional) y motor de consulta híbrida.
  - `dass_aos/cli.py`: subcomando `aos context`.
  - `dass_aos/memory.py`: integración de contexto relevante en `run_memory_refresh()`.
  - `dass_aos/bootstrap.py`, `dass_aos/update.py` / `dass_aos/constants.py`: asegurar `.aos/.cache/` en `.gitignore`.
  - `dass_aos/templates/hooks/session-start.md`, `dass_aos/templates/hooks/pre-task.md`, `dass_aos/sync.py`: documentación/flujo de uso de `aos context`.
  - `pyproject.toml`: extra opcional `rag`.

## Arquitectura y límites
- **Componentes tocados**: CLI (`cli.py`), memoria (`memory.py`), nuevo módulo `rag.py`, sincronización/plantillas de hooks e higiene de `.gitignore`.
- **Fronteras**:
  - `rag.py` **solo** lee archivos bajo `.aos/` (`knowledge/gotchas/`, `knowledge/lessons/LEDGER.md`, `decisions/`, `specs/`, `contracts/`, `plans/`) y escribe únicamente en `.aos/.cache/context.db`.
  - No indexa código fuente del proyecto (responsabilidad de `codebase-memory`) ni realiza llamadas de red en tiempo de consulta.
  - Si `fastembed` o `sqlite-vec` no están instalados (o fallan al cargar), `rag.py` degrada limpiamente a `FTS5` (BM25) sin lanzar excepción.

## Contratos
- **HTTP / Eventos**: sin cambios (herramienta CLI local).
- **Esquemas / salida CLI (`aos context --json`)**:
  ```json
  {
    "query": "string",
    "mode": "hybrid | lexical",
    "indexed_files": 0,
    "reindexed_files": 0,
    "results": [
      {
        "kind": "gotcha | lesson | decision | spec | contract | plan",
        "path": ".aos/...",
        "title": "string",
        "section": "string",
        "status": "string",
        "severity": "string",
        "score": 0.0,
        "snippet": "string"
      }
    ]
  }
  ```

## Modelo de datos (`.aos/.cache/context.db`)
- **Tablas**:
  - `meta(key TEXT PRIMARY KEY, value TEXT)` — versión de esquema, modelo de embeddings y dimensión.
  - `documents(path TEXT PRIMARY KEY, kind TEXT, title TEXT, status TEXT, severity TEXT, tags TEXT, mtime REAL, sha256 TEXT)` — control incremental (`CA-2`).
  - `chunks(id INTEGER PRIMARY KEY AUTOINCREMENT, doc_path TEXT, chunk_index INTEGER, section TEXT, content TEXT)` — contenido troceado por estructura (`CA-1`).
  - `chunks_fts` (`VIRTUAL TABLE USING fts5(content, title, section, tags, content='chunks', content_rowid='id')`) — índice léxico BM25.
  - `chunks_vec` (`VIRTUAL TABLE USING vec0(embedding float[N])`, creada solo cuando `sqlite-vec` y `fastembed` están activos) — índice vectorial (`CA-3`).
- **Migración / Idempotencia**:
  - Si cambia la versión del esquema o el modelo de embeddings en `meta`, o si el archivo `.db` está corrupto, se reconstruye `.aos/.cache/context.db` de forma transparente (al ser caché regenerable).
  - La indexación incremental compara `(mtime, sha256)` por archivo: elimina los chunks del archivo modificado/borrado e inserta los nuevos en una transacción.

## Estrategia de chunking y ranking
- **Chunking**:
  - Markdown (`gotchas`, `decisions`, `specs`, `plans`): extrae frontmatter (`title`, `status`, `severity`, `tags`) y divide por encabezados `## ` (manteniendo título + sección como contexto de cada chunk).
  - `LEDGER.md`: cada fila de tabla válida es un chunk individual (`kind = "lesson"`).
  - `contracts/` (`.yaml`, `.yml`, `.json`): chunk por documento o por bloque superior si supera el límite de caracteres.
- **Ranking híbrido y prioridad de dominio**:
  - En modo `hybrid`: RRF (`1 / (k + rank_fts) + 1 / (k + rank_vec)`) con `k = 60`.
  - En modo `lexical`: puntuación BM25 normalizada de `FTS5`.
  - Ajuste por metadatos: penalización ligera a ítems cerrados (`status` en `resuelta`, `resolved`, `completed`, `superseded`) y refuerzo a `gotcha` vigente de gravedad `critical`/`high`.

## Decisiones
- ADRs vinculados: `ADR-009-rag-local-conocimiento-sqlite-fastembed.md`

## Dependencias nuevas
- Extra opcional en `pyproject.toml`: `rag = ["fastembed>=0.3", "sqlite-vec>=0.1"]` (aprobado en `ADR-009`).

## Plan de prueba
- **Unitarias** (`tests/test_rag.py`):
  - Chunking de Markdown, `LEDGER.md` y contratos (`CA-1`).
  - Indexación incremental: sin cambios `reindexed_files == 0`; al modificar/borrar un archivo solo se actualiza ese (`CA-2`).
  - Búsqueda léxica (`FTS5`) sin dependencias `[rag]` y búsqueda híbrida con proveedor de embeddings mockeado (`CA-3`).
  - Consulta automática desde plan activo y caso sin plan activo (`CA-4`).
  - CLI `aos context` con `--kind`, `--limit`, `--reindex`, `--json` y salida de `aos refresh` (`CA-5`).
- **Verificación en vivo (`live-verify`)**:
  - Ejecutar `python -m dass_aos context "gotcha"` y `python -m dass_aos refresh` en el propio repositorio `dass-aos` y comprobar `.aos/.cache/context.db`, `.gitignore` y salida JSON/Markdown.

## Observabilidad
- `aos context` muestra el modo activo (`hybrid` o `lexical`) y estadísticas de indexación; en `--json` incluye `mode`, `indexed_files` y `reindexed_files`.
- `aos doctor` puede reportar como `INFO` si `[rag]` no está instalado (operando en modo léxico).

## Riesgos técnicos
- **Entornos Python sin `sqlite-vec` o sin descarga de modelo ONNX**: mitigado con *fallback* automático a `FTS5` (sin error) y tests independientes con mock del embedder.
- **Consultas con caracteres especiales en `FTS5`** (guiones, puntos, dos puntos en rutas o `CA-1`): mitigado tokenizando/escapando términos de la query antes de pasarlos a `MATCH`.

## Referencias
- **Plan**: pendiente (`aos plan new feature --title "RAG local de conocimiento"`)
