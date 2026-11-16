---
id: 202611160856
type: decision
status: vigente
created: 2026-11-16
---

# ADR-009: RAG local de conocimiento con SQLite (FTS5 + sqlite-vec) y fastembed opcional

## Contexto
El núcleo de `dass-aos` no tiene dependencias obligatorias en tiempo de ejecución (`pyproject.toml`, `requires-python = ">=3.8"`), y las herramientas externas pesadas se declaran como extras opcionales (por ejemplo `scan = ["semgrep", "checkov"]`).

Para dotar al agente de recuperación rápida de conocimiento en `.aos/` (`001-rag-local-de-conocimiento.prd.md`), se necesita:
1. Un índice persistente y consultable en milisegundos sin levantar servicios ni procesos en segundo plano.
2. Búsqueda semántica mediante embeddings locales + búsqueda léxica exacta para identificadores, rutas y códigos de error.
3. Degradación limpia cuando el usuario no instale dependencias de ML.

## Decisión
1. **Almacenamiento único en SQLite (`.aos/.cache/context.db`)**:
   - Se usa `sqlite3` de la biblioteca estándar de Python para tablas de documentos, *chunks* y tabla virtual `FTS5` (ranking BM25).
   - Cuando está disponible `sqlite-vec`, se almacena y consulta la tabla vectorial `vec0` en el mismo archivo `.db`.
   - `.aos/.cache/` se excluye en `.gitignore` por tratarse de un índice local regenerable desde `.aos/`.
2. **Extra opcional `[rag]` en `pyproject.toml`**:
   - Se declara `rag = ["fastembed>=0.3", "sqlite-vec>=0.1"]` en `[project.optional-dependencies]`.
   - `fastembed` ejecuta modelos ONNX ligeros en CPU sin requerir PyTorch ni servidor externo.
3. **Búsqueda híbrida con *fallback* automático**:
   - Con `[rag]` instalado: búsqueda híbrida combinando similitud coseno (`sqlite-vec`) y `FTS5` (BM25) mediante *Reciprocal Rank Fusion* (RRF), ponderando metadatos (`status` vigente/abierto y `severity`).
   - Sin `[rag]` instalado: *fallback* automático y transparente a `FTS5` (BM25), indicando el modo activo (`lexical` vs `hybrid`).

## Consecuencias
- **Positivas**: Cero dependencias obligatorias nuevas para `pip install dass-aos`; un único archivo `.db` sin daemons; latencia de consulta local en milisegundos; funciona offline.
- **Negativas / Trade-offs**: El primer uso en modo `hybrid` descarga el modelo ONNX de `fastembed` a la caché local del usuario; entornos sin `sqlite-vec` o `fastembed` operan en modo solo léxico (`FTS5`).
