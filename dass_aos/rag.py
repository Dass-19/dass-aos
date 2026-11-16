"""Local knowledge RAG over `.aos/` using SQLite (FTS5 + optional sqlite-vec/fastembed)."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .constants import AOS_DIR_NAME

SCHEMA_VERSION = "1"
DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"
MAX_CHUNK_CHARS = 1400
CLOSED_STATUSES = {"resuelta", "resolved", "completed", "superseded", "cerrada"}
SEVERITY_BOOST = {"critical": 1.35, "high": 1.20, "medium": 1.05}
RRF_K = 60


@dataclass
class ChunkRecord:
    """Single searchable chunk extracted from a `.aos/` knowledge artifact."""

    doc_path: str
    kind: str
    title: str
    section: str
    status: str
    severity: str
    tags: str
    content: str


@dataclass
class SearchHit:
    """Ranked result returned by `search_context`."""

    kind: str
    path: str
    title: str
    section: str
    status: str
    severity: str
    score: float
    snippet: str


@dataclass
class ContextResponse:
    """Structured response for `aos context` and `run_memory_refresh`."""

    query: str
    mode: str
    indexed_files: int
    reindexed_files: int
    results: List[SearchHit]
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "mode": self.mode,
            "indexed_files": self.indexed_files,
            "reindexed_files": self.reindexed_files,
            "note": self.note,
            "results": [asdict(r) for r in self.results],
        }


class Embedder:
    """Minimal interface for local embedding providers."""

    model_name: str = DEFAULT_EMBED_MODEL

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        raise NotImplementedError


class FastEmbedProvider(Embedder):
    """Optional local ONNX embedder backed by `fastembed`."""

    def __init__(self, model_name: str = DEFAULT_EMBED_MODEL) -> None:
        from fastembed import TextEmbedding  # type: ignore

        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name)

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        return [list(map(float, vec)) for vec in self._model.embed(list(texts))]


def load_optional_rag_backend() -> Tuple[Optional[Embedder], Optional[Any]]:
    """Return `(embedder, sqlite_vec_module)` when `[rag]` extras are installed, else `(None, None)`."""
    try:
        import sqlite_vec  # type: ignore
        embedder = FastEmbedProvider()
        return embedder, sqlite_vec
    except Exception:
        return None, None


def _connect(db_path: Path, sqlite_vec_mod: Optional[Any] = None) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    if sqlite_vec_mod is not None:
        conn.enable_load_extension(True)
        sqlite_vec_mod.load(conn)
        conn.enable_load_extension(False)
    return conn


def _parse_frontmatter(text: str, fallback_title: str) -> Tuple[Dict[str, str], str]:
    """Extract simple YAML frontmatter keys and return `(meta, body)`."""
    lines = text.splitlines()
    meta: Dict[str, str] = {"title": "", "status": "", "severity": "", "tags": ""}
    body_start = 0

    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                body_start = i + 1
                break
            key, _, val = lines[i].partition(":")
            key = key.strip().lower()
            val = val.strip().strip("\"'")
            if key in meta:
                if key == "tags":
                    val = val.strip("[]")
                meta[key] = val

    body = "\n".join(lines[body_start:])
    if not meta["title"]:
        for line in lines[body_start:]:
            if line.startswith("# "):
                meta["title"] = line[2:].strip()
                break
    if not meta["title"]:
        meta["title"] = fallback_title
    return meta, body


def _split_long_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> List[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    parts: List[str] = []
    current: List[str] = []
    current_len = 0
    for para in re.split(r"\n{2,}", text):
        para = para.strip()
        if not para:
            continue
        if current and current_len + len(para) + 2 > max_chars:
            parts.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += len(para) + (2 if current else 0)
    if current:
        parts.append("\n\n".join(current))
    return parts


def _chunk_markdown(rel_path: str, kind: str, text: str, fallback_title: str) -> Tuple[Dict[str, str], List[ChunkRecord]]:
    meta, body = _parse_frontmatter(text, fallback_title)
    sections: List[Tuple[str, str]] = []
    current_heading = "Resumen"
    buf: List[str] = []

    for line in body.splitlines():
        if line.startswith("## "):
            content = "\n".join(buf).strip()
            if content:
                sections.append((current_heading, content))
            current_heading = line[3:].strip() or "Sección"
            buf = []
        else:
            buf.append(line)
    tail = "\n".join(buf).strip()
    if tail:
        sections.append((current_heading, tail))

    chunks: List[ChunkRecord] = []
    for heading, sec_text in sections:
        for piece in _split_long_text(sec_text):
            chunks.append(
                ChunkRecord(
                    doc_path=rel_path,
                    kind=kind,
                    title=meta["title"],
                    section=heading,
                    status=meta["status"].lower(),
                    severity=meta["severity"].lower(),
                    tags=meta["tags"],
                    content=piece,
                )
            )
    if not chunks and meta["title"]:
        chunks.append(
            ChunkRecord(
                doc_path=rel_path,
                kind=kind,
                title=meta["title"],
                section="Resumen",
                status=meta["status"].lower(),
                severity=meta["severity"].lower(),
                tags=meta["tags"],
                content=meta["title"],
            )
        )
    return meta, chunks


def _chunk_ledger(rel_path: str, text: str) -> Tuple[Dict[str, str], List[ChunkRecord]]:
    meta = {"title": "LEDGER de Lecciones", "status": "vigente", "severity": "", "tags": "lessons"}
    chunks: List[ChunkRecord] = []
    for line in text.splitlines():
        if not line.startswith("|") or line.startswith("|-") or line.startswith("| Fecha"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4 or not any(cells):
            continue
        if cells[1].lstrip("`").startswith("<"):
            continue
        content = f"{cells[0]} | {cells[1]} | {cells[2]} | {cells[3]}"
        chunks.append(
            ChunkRecord(
                doc_path=rel_path,
                kind="lesson",
                title=cells[1],
                section=cells[0],
                status="vigente",
                severity="",
                tags="lessons",
                content=content,
            )
        )
    return meta, chunks


def _chunk_contract(rel_path: str, text: str, name: str) -> Tuple[Dict[str, str], List[ChunkRecord]]:
    meta = {"title": name, "status": "vigente", "severity": "", "tags": "contract"}
    chunks = [
        ChunkRecord(
            doc_path=rel_path,
            kind="contract",
            title=name,
            section="Contrato",
            status="vigente",
            severity="",
            tags="contract",
            content=piece,
        )
        for piece in _split_long_text(text)
    ]
    return meta, chunks


def discover_knowledge_files(project_root: Path) -> List[Tuple[Path, str]]:
    """Collect `(path, kind)` pairs for `.aos/` knowledge artifacts."""
    aos_dir = project_root / AOS_DIR_NAME
    if not aos_dir.exists():
        return []

    found: List[Tuple[Path, str]] = []
    specs: List[Tuple[Path, str, Tuple[str, ...]]] = [
        (aos_dir / "knowledge" / "gotchas", "gotcha", (".md",)),
        (aos_dir / "decisions", "decision", (".md",)),
        (aos_dir / "specs", "spec", (".md",)),
        (aos_dir / "plans" / "active", "plan", (".md",)),
        (aos_dir / "plans" / "completed", "plan", (".md",)),
    ]
    for directory, kind, exts in specs:
        if directory.exists():
            for p in sorted(directory.iterdir()):
                if p.is_file() and p.suffix.lower() in exts and p.name.lower() != "readme.md":
                    found.append((p, kind))

    ledger = aos_dir / "knowledge" / "lessons" / "LEDGER.md"
    if ledger.is_file():
        found.append((ledger, "lesson"))

    contracts_dir = aos_dir / "contracts"
    if contracts_dir.exists():
        for p in sorted(contracts_dir.rglob("*")):
            if p.is_file() and p.suffix.lower() in {".yaml", ".yml", ".json"} and not p.name.lower().startswith("readme"):
                found.append((p, "contract"))

    return found


def _init_schema(conn: sqlite3.Connection, embed_dim: Optional[int], model_name: str) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS documents (
            path TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            severity TEXT NOT NULL,
            tags TEXT NOT NULL,
            mtime REAL NOT NULL,
            sha256 TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_path TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            section TEXT NOT NULL,
            content TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            content,
            title,
            section,
            tags
        );
        """
    )
    if embed_dim is not None:
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(chunk_id INTEGER PRIMARY KEY, embedding float[{embed_dim}])"
        )
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('embedder_model', ?)", (model_name if embed_dim else "none",))
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('embed_dim', ?)", (str(embed_dim or 0),))
    conn.commit()


def _schema_needs_rebuild(conn: sqlite3.Connection, want_model: str) -> bool:
    try:
        rows = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    except sqlite3.OperationalError:
        return True
    if rows.get("schema_version") != SCHEMA_VERSION:
        return True
    if rows.get("embedder_model") != want_model:
        return True
    return False


def _pack_vec(vec: Sequence[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _delete_document(conn: sqlite3.Connection, doc_path: str, has_vec: bool) -> None:
    chunk_ids = [r[0] for r in conn.execute("SELECT id FROM chunks WHERE doc_path = ?", (doc_path,)).fetchall()]
    for cid in chunk_ids:
        conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (cid,))
        if has_vec:
            conn.execute("DELETE FROM chunks_vec WHERE chunk_id = ?", (cid,))
    conn.execute("DELETE FROM chunks WHERE doc_path = ?", (doc_path,))
    conn.execute("DELETE FROM documents WHERE path = ?", (doc_path,))


def _extract_chunks(project_root: Path, path: Path, kind: str, text: str) -> Tuple[Dict[str, str], List[ChunkRecord]]:
    rel = path.relative_to(project_root).as_posix()
    if kind == "lesson":
        return _chunk_ledger(rel, text)
    if kind == "contract":
        return _chunk_contract(rel, text, path.name)
    return _chunk_markdown(rel, kind, text, path.stem)


def index_knowledge(
    project_root: Path,
    reindex: bool = False,
    embedder: Optional[Embedder] = None,
    sqlite_vec_mod: Optional[Any] = None,
) -> Tuple[int, int, str]:
    """Incrementally index `.aos/` knowledge into `.aos/.cache/context.db`.

    Returns `(indexed_files, reindexed_files, mode)`.
    """
    db_path = project_root / AOS_DIR_NAME / ".cache" / "context.db"
    if embedder is None and sqlite_vec_mod is None:
        embedder, sqlite_vec_mod = load_optional_rag_backend()

    has_vec = embedder is not None and sqlite_vec_mod is not None
    want_model = embedder.model_name if has_vec else "none"
    mode = "hybrid" if has_vec else "lexical"

    if reindex and db_path.exists():
        db_path.unlink()

    conn = _connect(db_path, sqlite_vec_mod if has_vec else None)
    try:
        if _schema_needs_rebuild(conn, want_model):
            conn.close()
            if db_path.exists():
                db_path.unlink()
            conn = _connect(db_path, sqlite_vec_mod if has_vec else None)
            embed_dim: Optional[int] = None
            if has_vec:
                probe = embedder.embed_texts(["probe"])
                embed_dim = len(probe[0]) if probe else 0
            _init_schema(conn, embed_dim if embed_dim else None, want_model)

        existing = {
            r["path"]: (r["mtime"], r["sha256"])
            for r in conn.execute("SELECT path, mtime, sha256 FROM documents").fetchall()
        }
        files = discover_knowledge_files(project_root)
        current_paths = {p.relative_to(project_root).as_posix() for p, _ in files}

        reindexed = 0
        for stale in set(existing) - current_paths:
            _delete_document(conn, stale, has_vec)
            reindexed += 1

        pending_vecs: List[Tuple[int, str]] = []
        for path, kind in files:
            rel = path.relative_to(project_root).as_posix()
            mtime = path.stat().st_mtime
            prev = existing.get(rel)
            if prev is not None and prev[0] == mtime:
                continue

            raw = path.read_text(encoding="utf-8", errors="replace")
            digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            if prev is not None and prev[1] == digest:
                conn.execute("UPDATE documents SET mtime = ? WHERE path = ?", (mtime, rel))
                continue

            _delete_document(conn, rel, has_vec)
            meta, chunks = _extract_chunks(project_root, path, kind, raw)
            conn.execute(
                "INSERT INTO documents(path, kind, title, status, severity, tags, mtime, sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    rel,
                    kind,
                    meta.get("title", path.stem),
                    meta.get("status", "").lower(),
                    meta.get("severity", "").lower(),
                    meta.get("tags", ""),
                    mtime,
                    digest,
                ),
            )
            for idx, ch in enumerate(chunks):
                cur = conn.execute(
                    "INSERT INTO chunks(doc_path, chunk_index, section, content) VALUES (?, ?, ?, ?)",
                    (ch.doc_path, idx, ch.section, ch.content),
                )
                cid = int(cur.lastrowid)
                conn.execute(
                    "INSERT INTO chunks_fts(rowid, content, title, section, tags) VALUES (?, ?, ?, ?, ?)",
                    (cid, ch.content, ch.title, ch.section, ch.tags),
                )
                if has_vec:
                    pending_vecs.append((cid, f"{ch.title}\n{ch.section}\n{ch.content}"))
            reindexed += 1

        if has_vec and pending_vecs:
            vectors = embedder.embed_texts([txt for _, txt in pending_vecs])
            for (cid, _), vec in zip(pending_vecs, vectors):
                conn.execute("INSERT INTO chunks_vec(chunk_id, embedding) VALUES (?, ?)", (cid, _pack_vec(vec)))

        conn.commit()
        return len(files), reindexed, mode
    finally:
        conn.close()


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[\w]+", query, re.UNICODE)
    if not tokens:
        return ""
    return " OR ".join(f'"{t}"' for t in tokens[:24])


def _metadata_factor(kind: str, status: str, severity: str) -> float:
    if status in CLOSED_STATUSES:
        return 0.65
    if kind == "gotcha":
        return SEVERITY_BOOST.get(severity, 1.0)
    return 1.0


def _make_snippet(text: str, max_len: int = 220) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= max_len else compact[: max_len - 3].rstrip() + "..."


def resolve_default_query(project_root: Path) -> str:
    """Derive a query from the next pending `- [ ]` task in `.aos/plans/active/`."""
    from .memory import get_active_plan_info

    info = get_active_plan_info(project_root)
    if not info:
        return ""
    _, next_task = info
    if not next_task or next_task.startswith("(no hay tareas"):
        return ""
    return next_task


def search_context(
    project_root: Path,
    query: Optional[str] = None,
    *,
    kind: Optional[str] = None,
    exclude_kinds: Optional[Sequence[str]] = None,
    limit: int = 5,
    reindex: bool = False,
    embedder: Optional[Embedder] = None,
    sqlite_vec_mod: Optional[Any] = None,
) -> ContextResponse:
    """Index incrementally and retrieve top matching `.aos/` chunks."""
    resolved_query = (query or "").strip() or resolve_default_query(project_root)
    if embedder is None and sqlite_vec_mod is None:
        embedder, sqlite_vec_mod = load_optional_rag_backend()

    indexed, reindexed, mode = index_knowledge(
        project_root, reindex=reindex, embedder=embedder, sqlite_vec_mod=sqlite_vec_mod
    )
    if not resolved_query:
        return ContextResponse(
            query="",
            mode=mode,
            indexed_files=indexed,
            reindexed_files=reindexed,
            results=[],
            note="Sin consulta ni tarea pendiente en `.aos/plans/active/`.",
        )

    db_path = project_root / AOS_DIR_NAME / ".cache" / "context.db"
    has_vec = mode == "hybrid"
    conn = _connect(db_path, sqlite_vec_mod if has_vec else None)
    try:
        fts_q = _fts_query(resolved_query)
        fts_ranks: Dict[int, int] = {}
        if fts_q:
            sql = (
                "SELECT chunks.id, bm25(chunks_fts) AS rank_score "
                "FROM chunks_fts JOIN chunks ON chunks.id = chunks_fts.rowid "
                "JOIN documents ON documents.path = chunks.doc_path "
                "WHERE chunks_fts MATCH ? "
            )
            params: List[Any] = [fts_q]
            if kind:
                sql += "AND documents.kind = ? "
                params.append(kind)
            sql += "ORDER BY rank_score LIMIT ?"
            params.append(max(limit * 4, 20))
            for idx, row in enumerate(conn.execute(sql, params).fetchall(), start=1):
                fts_ranks[int(row["id"])] = idx

        vec_ranks: Dict[int, int] = {}
        if has_vec and embedder is not None:
            q_vecs = embedder.embed_texts([resolved_query])
            if q_vecs:
                q_blob = _pack_vec(q_vecs[0])
                vec_sql = (
                    "SELECT v.chunk_id, v.distance "
                    "FROM chunks_vec v JOIN chunks c ON c.id = v.chunk_id "
                    "JOIN documents d ON d.path = c.doc_path "
                    "WHERE v.embedding MATCH ? AND k = ? "
                )
                v_params: List[Any] = [q_blob, max(limit * 4, 20)]
                if kind:
                    vec_sql += "AND d.kind = ? "
                    v_params.append(kind)
                vec_sql += "ORDER BY v.distance"
                for idx, row in enumerate(conn.execute(vec_sql, v_params).fetchall(), start=1):
                    vec_ranks[int(row["chunk_id"])] = idx

        candidate_ids = set(fts_ranks) | set(vec_ranks)
        if not candidate_ids:
            return ContextResponse(
                query=resolved_query,
                mode=mode,
                indexed_files=indexed,
                reindexed_files=reindexed,
                results=[],
                note="Sin coincidencias para la consulta.",
            )

        excluded = set(exclude_kinds or ())
        placeholders = ",".join("?" for _ in candidate_ids)
        rows = conn.execute(
            f"""
            SELECT c.id, c.doc_path, c.section, c.content,
                   d.kind, d.title, d.status, d.severity
            FROM chunks c
            JOIN documents d ON d.path = c.doc_path
            WHERE c.id IN ({placeholders})
            """,
            tuple(candidate_ids),
        ).fetchall()

        hits: List[SearchHit] = []
        for row in rows:
            if row["kind"] in excluded:
                continue
            cid = int(row["id"])
            rrf = 0.0
            if cid in fts_ranks:
                rrf += 1.0 / (RRF_K + fts_ranks[cid])
            if cid in vec_ranks:
                rrf += 1.0 / (RRF_K + vec_ranks[cid])
            factor = _metadata_factor(row["kind"], row["status"], row["severity"])
            hits.append(
                SearchHit(
                    kind=row["kind"],
                    path=row["doc_path"],
                    title=row["title"],
                    section=row["section"],
                    status=row["status"],
                    severity=row["severity"],
                    score=round(rrf * factor, 6),
                    snippet=_make_snippet(row["content"]),
                )
            )
        hits.sort(key=lambda h: h.score, reverse=True)
        return ContextResponse(
            query=resolved_query,
            mode=mode,
            indexed_files=indexed,
            reindexed_files=reindexed,
            results=hits[:limit],
        )
    finally:
        conn.close()


def format_context_markdown(resp: ContextResponse) -> str:
    """Format `ContextResponse` as concise Markdown for terminal or agent injection."""
    lines = [
        f"# DASS-AOS · Contexto ({resp.mode})",
        f"_Consulta: `{resp.query}` · Indexados: {resp.indexed_files} (actualizados: {resp.reindexed_files})_"
        if resp.query
        else f"_Indexados: {resp.indexed_files} (actualizados: {resp.reindexed_files})_",
        "",
    ]
    if not resp.results:
        lines.append(f"- {resp.note or 'Sin coincidencias.'}")
        return "\n".join(lines)

    for hit in resp.results:
        meta_bits = [hit.kind.upper()]
        if hit.severity:
            meta_bits.append(hit.severity)
        if hit.status:
            meta_bits.append(hit.status)
        badge = " · ".join(meta_bits)
        lines.append(f"- **[{badge}] {hit.title}** › _{hit.section}_ (`{hit.path}`, score={hit.score:.4f})")
        lines.append(f"  > {hit.snippet}")
    return "\n".join(lines)


def run_context(
    project_root: Path,
    query: Optional[str] = None,
    *,
    kind: Optional[str] = None,
    limit: int = 5,
    reindex: bool = False,
    as_json: bool = False,
    embedder_factory: Optional[Callable[[], Tuple[Optional[Embedder], Optional[Any]]]] = None,
) -> ContextResponse:
    """CLI entry point for `aos context`."""
    embedder, vec_mod = embedder_factory() if embedder_factory else (None, None)
    resp = search_context(
        project_root,
        query=query,
        kind=kind,
        limit=limit,
        reindex=reindex,
        embedder=embedder,
        sqlite_vec_mod=vec_mod,
    )
    if as_json:
        print(json.dumps(resp.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_context_markdown(resp))
    return resp
