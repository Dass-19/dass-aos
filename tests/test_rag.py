import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from dass_aos.cli import main
from dass_aos.memory import run_memory_refresh
from dass_aos.rag import index_knowledge, load_optional_rag_backend, search_context
from dass_aos.sync import ensure_gitignore


class TestLocalKnowledgeRAG(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.aos_dir = self.temp_dir / ".aos"
        for sub in (
            "knowledge/gotchas",
            "knowledge/lessons",
            "decisions",
            "specs",
            "contracts/http",
            "plans/active",
        ):
            (self.aos_dir / sub).mkdir(parents=True, exist_ok=True)

        (self.aos_dir / "knowledge/gotchas/outbox-drain.md").write_text(
            "---\ntitle: Outbox sin drenar\nseverity: high\nstatus: vigente\ntags: [outbox, cdc]\n---\n\n"
            "## Síntoma\nLos eventos quedan en tabla outbox sin publicarse a Kafka.\n\n"
            "## Prevención\nVerificar worker de relay antes de desplegar.\n",
            encoding="utf-8",
        )
        (self.aos_dir / "knowledge/gotchas/old-resolved.md").write_text(
            "---\ntitle: Outbox antiguo resuelto\nseverity: high\nstatus: resuelta\n---\n\n"
            "## Síntoma\nProblema de outbox ya corregido en v1.\n",
            encoding="utf-8",
        )
        (self.aos_dir / "knowledge/lessons/LEDGER.md").write_text(
            "# LEDGER\n\n| Fecha | Artefacto | Evidencia | Efecto |\n|---|---|---|---|\n"
            "| 2026-11-10 | `outbox` | `pytest -k outbox` | Validar relay en staging |\n",
            encoding="utf-8",
        )
        (self.aos_dir / "decisions/ADR-001-outbox.md").write_text(
            "# ADR-001: Uso de Outbox transaccional\n\n## Decisión\nPublicar eventos mediante tabla outbox.\n",
            encoding="utf-8",
        )
        (self.aos_dir / "specs/001-pagos.prd.md").write_text(
            "# PRD: Pagos\n\n## Criterios\nProcesar cobros con idempotencia.\n",
            encoding="utf-8",
        )
        (self.aos_dir / "contracts/http/pagos.yaml").write_text(
            "openapi: 3.0.0\npaths:\n  /pagos:\n    post:\n      summary: Crear pago\n",
            encoding="utf-8",
        )
        (self.aos_dir / "plans/active/001-pagos.md").write_text(
            "# Plan Pagos\n\n- [ ] Revisar relay de outbox y endpoint /pagos\n",
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_index_chunks_all_aos_sources_and_creates_db(self):
        with mock.patch("dass_aos.rag.load_optional_rag_backend", return_value=(None, None)):
            indexed, reindexed, mode = index_knowledge(self.temp_dir)
        self.assertEqual(mode, "lexical")
        self.assertEqual(indexed, 7)
        self.assertEqual(reindexed, 7)
        self.assertTrue((self.aos_dir / ".cache" / "context.db").exists())

    def test_incremental_indexing_skips_unchanged_and_updates_modified(self):
        with mock.patch("dass_aos.rag.load_optional_rag_backend", return_value=(None, None)):
            _, first_reindexed, _ = index_knowledge(self.temp_dir)
            self.assertEqual(first_reindexed, 7)

            _, second_reindexed, _ = index_knowledge(self.temp_dir)
            self.assertEqual(second_reindexed, 0)

            adr = self.aos_dir / "decisions/ADR-001-outbox.md"
            adr.write_text("# ADR-001: Outbox\n\n## Decisión\nActualizado con retry exponencial.\n", encoding="utf-8")
            os.utime(adr, (adr.stat().st_mtime + 5, adr.stat().st_mtime + 5))

            _, third_reindexed, _ = index_knowledge(self.temp_dir)
            self.assertEqual(third_reindexed, 1)

            adr.unlink()
            indexed_after_del, fourth_reindexed, _ = index_knowledge(self.temp_dir)
            self.assertEqual(indexed_after_del, 6)
            self.assertEqual(fourth_reindexed, 1)

    def test_lexical_search_prioritizes_open_high_severity_gotcha(self):
        with mock.patch("dass_aos.rag.load_optional_rag_backend", return_value=(None, None)):
            resp = search_context(self.temp_dir, query="outbox relay", kind="gotcha", limit=5)
        self.assertEqual(resp.mode, "lexical")
        self.assertGreaterEqual(len(resp.results), 2)
        self.assertEqual(resp.results[0].title, "Outbox sin drenar")
        self.assertGreater(resp.results[0].score, resp.results[1].score)

    def test_default_query_from_active_plan_and_no_plan(self):
        with mock.patch("dass_aos.rag.load_optional_rag_backend", return_value=(None, None)):
            resp = search_context(self.temp_dir, query=None, limit=3)
            self.assertIn("outbox", resp.query.lower())
            self.assertTrue(resp.results)

            (self.aos_dir / "plans/active/001-pagos.md").unlink()
            empty_resp = search_context(self.temp_dir, query=None, limit=3)
            self.assertEqual(empty_resp.query, "")
            self.assertEqual(empty_resp.results, [])
            self.assertTrue(empty_resp.note)

    def test_cli_context_json_and_memory_refresh_integration(self):
        buf = io.StringIO()
        with mock.patch("dass_aos.rag.load_optional_rag_backend", return_value=(None, None)):
            with redirect_stdout(buf):
                rc = main(["context", "outbox", "--kind", "gotcha", "--json", "--project-root", str(self.temp_dir)])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["mode"], "lexical")
        self.assertEqual(payload["results"][0]["kind"], "gotcha")

        with mock.patch("dass_aos.rag.load_optional_rag_backend", return_value=(None, None)):
            with redirect_stdout(io.StringIO()):
                md = run_memory_refresh(self.temp_dir)
        self.assertIn("## 8. Contexto Relevante (RAG)", md)
        self.assertIn("Outbox sin drenar", md)

    def test_hybrid_mode_when_optional_backend_is_installed(self):
        embedder, vec_mod = load_optional_rag_backend()
        if embedder is None or vec_mod is None:
            self.skipTest("optional [rag] extras (fastembed, sqlite-vec) not installed")
        resp = search_context(self.temp_dir, query="eventos kafka sin publicar", limit=3, embedder=embedder, sqlite_vec_mod=vec_mod)
        self.assertEqual(resp.mode, "hybrid")
        self.assertTrue(resp.results)

    def test_ensure_gitignore_adds_aos_cache(self):
        (self.temp_dir / ".git").mkdir()
        (self.temp_dir / ".gitignore").write_text(".aos/native/\n", encoding="utf-8")
        ensure_gitignore(self.temp_dir)
        content = (self.temp_dir / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".aos/.cache/", content.splitlines())


if __name__ == "__main__":
    unittest.main()
