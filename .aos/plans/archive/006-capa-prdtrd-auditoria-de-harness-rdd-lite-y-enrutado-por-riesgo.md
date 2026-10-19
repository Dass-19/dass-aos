---
id: 202610191241
type: plan
status: done
priority: medium
tags: [plan/feature]
created: 2026-10-19
prd:
trd:
---

# Plan: Feature — Capa PRD/TRD, auditoría de harness, RDD-lite y enrutado por riesgo

> Objetivo (Definition of Done): el motor gana la cadena PRD → TRD → contratos → plan, un audit de harness de solo lectura (`aos doctor`), un estado derivado de archivos (`aos status`), la revisión con recibo y el enrutado por riesgo en lugar del conteo de archivos. Todo con tests y ejercitado en vivo sobre proyectos temporales.

## Contexto y Archivos Afectados
- PRD/TRD: **no aplica** — es un cambio de motor y de reglas internas; el requisito es el análisis de
  `google-research/harness2` y `Gentleman-Programming/gentle-ai` acordado con el usuario.
- Archivos previstos: `dass_aos/{specs,doctor,status,backup}.py`, `templates/specs/`,
  `templates/knowledge/lessons/`, `hooks/*`, `plans/templates/*`, `sync.py`, `cli.py`, `memory.py`,
  `bootstrap.py`, `native/{base,files}.py`, `docs/CODE-GRAPH-OPTIONS.md`, `README.md`,
  `docs/ARCHITECTURE.md`, 5 suites nuevas de test.
- ADRs vinculados: ADR-007 (requisitos + grafo), ADR-008 (riesgo + recibo).
- Gotchas a considerar: `sync` regenera las skills con marcador; los hooks y las plantillas de plan
  son del proyecto y no se sincronizan (ADR-006 §7).
- Contratos a crear/actualizar: ninguno (el motor no publica HTTP/eventos).
- Riesgo (ADR-008): **alto** — cambia reglas centrales del ciclo de vida, escribe archivos del
  usuario y afecta a todos los proyectos; profundidad de revisión → 4R con recibo.

> La spec se cita, nunca se parafrasea: los handoffs apuntan a la ruta y a la sección del PRD/TRD.

## Fases de Ejecución Atómica
> Cada fase termina con su línea `Gate:` (comando exacto y resultado esperado). Flujo completo en la skill `phased-delivery`. El tamaño se decide por riesgo y comprensión, no por número de archivos (ADR-008).

- [x] Fase 1: Línea base y ADRs (riesgo alto → este plan)
  - Línea base: `aos verify` → 68 tests OK, ruff limpio, `aos scan --dry-run` exit 0
  - `ADR-007` (PRD/TRD + grafo por defecto) y `ADR-008` (riesgo + recibo) escritos en `.aos/decisions/`
  - Gate: ambos ADR con contexto, decisión, alternativas y consecuencias ✅
- [x] Fase 2: Capa PRD/TRD (`aos spec new prd|trd`)
  - `dass_aos/specs.py` (NNN compartido por título), `templates/specs/{README.md,templates/{prd,trd}.md}`,
    `templates/skills/specs/spec-driven.md`, `tests/test_specs.py`
  - `cli.py`, `bootstrap.py` (crea `.aos/specs/`), `memory.py` §3, hooks `session-start`/`pre-task`,
    las 4 plantillas de plan, README §5.0 y `docs/ARCHITECTURE.md` §6
  - Defecto encontrado y corregido: las plantillas se copiaban dentro de `.aos/specs/` y se
    confundían con specs reales → ahora viven en `.aos/specs/templates/`
  - Gate: `aos spec new prd`/`trd` en proyecto temporal crea `001-x.prd.md` y `001-x.trd.md`;
    `aos refresh` lista las specs abiertas ✅
- [x] Fase 3: Auditoría de harness y escrituras seguras
  - `dass_aos/{doctor,backup}.py`, `templates/knowledge/lessons/LEDGER.md`, `memory.py` §6 (lecciones)
  - `cost:` en las 13 skills del motor; `deny_paths` en `config.json` (bootstrap + este repo) y
    guard en `hooks/pre_commit.py`; snapshots en `sync` y en `native/{base,files}.py`
  - Frontera de evidencia en el bloque gestionado (`sync.build_managed_block`)
  - Defectos corregidos: falso positivo con skills condicionales; `applies_when` malformado
    tumbaba el audit entero → ahora es un `error` reportado, no un crash; poda de snapshots
  - Gate: `aos doctor` en este repo → 0 errores, 0 avisos, 3 info; tests de doctor/backup/pre-commit ✅
- [x] Fase 4: RDD-lite y `aos status`
  - `adversarial-review.md` reescrita (recibo, tiers pasivo/medio/alto = 0/1/4R, una corrección,
    acuse); `dass_aos/status.py` + `tests/test_status.py`
  - Gate: `aos status` devuelve `Ready` sin plan, `Needs decision` al crear el plan feature,
    `Working` al marcar la Fase 1; `--json` parseable ✅
- [x] Fase 5: Enrutado por riesgo
  - `sync.build_managed_block` (ciclo de vida), `phased-delivery.md` (§0.5 tabla de tiers + motivos
    de delegación con umbral), README §5.1
  - Gate: ninguna regla del motor sigue midiendo el tamaño por número de archivos (revisado con
    `grep` sobre `templates/`, `.aos/` y `AGENTS.md`) ✅
- [x] Fase 6: Comparativa de grafos (solo documento)
  - `docs/CODE-GRAPH-OPTIONS.md`: comparativa, decisión y condición de revisión; `.aos/mcp-config.json`
    **sin tocar**
  - Gate: `codebase-memory` sigue siendo el único servidor; ningún `codegraph` en `.aos/` ✅
- [x] Fase 7: Verificación en vivo y cierre
  - `aos verify` → lint + 109 tests OK; `aos scan --dry-run` → exit 0
  - `aos doctor` → 0 errores / 0 avisos; `aos status` sobre el repo → estado coherente
  - `aos sync` + `adapt-native claude-code --yes` y `antigravity --yes`; versión 0.7.0
  - Gate: todo verde y CLI ejercitado en vivo (spec, status, doctor, duplicate-spec) ✅

## Recibo de Revisión (RDD)
- Candidato: árbol de trabajo tras la Fase 7 · 8 archivos nuevos de motor + 5 suites + docs
- Tier: **alto** (riesgo nombrado: reglas centrales, escritura sobre archivos del usuario)
- Lentes: 4R (Risk · Resilience · Readability · Reliability)

### Acuse
- Confirmados y corregidos: plantillas contaminando `.aos/specs/`; rama inalcanzable en el check de
  skills; `applies_when` malformado derribando el audit; poda de snapshots dejando 21; mensaje de
  error de `spec new` nombrando la pareja equivocada; `--json` con no-ASCII en pipes de Windows.
- Refutados: «`doctor` debería bloquear commits» (ADR-008: diagnóstico, nunca gate);
  «`codegraph` como default» (ver `docs/CODE-GRAPH-OPTIONS.md`).
- Pendientes: sustituir el `git stash create` del recibo por algo que capture también no rastreados,
  si en la práctica se vuelve un problema; validar la tabla de motivos de delegación con mediciones
  propias (las de Gentle-AI son n=1).
- Gates repetidos: `aos verify` → verde · `aos scan --dry-run` → exit 0 · `aos doctor` → 0 errores.
- Documentos corregidos: `README.md`, `docs/ARCHITECTURE.md`, `docs/CODE-GRAPH-OPTIONS.md`,
  hooks, plantillas de plan y `.aos/knowledge/lessons/LEDGER.md`.

## Registro de Preguntas y Decisiones (Discovery Trail)
- **Pregunta:** ¿PRD/TRD dentro de `.aos/` en una carpeta nueva?
- **Opciones:** `.aos/specs/` · dentro de `.aos/plans/` · junto a `.aos/contracts/`
- **Decisión:** `.aos/specs/`, con `NNN` compartido con el plan y el `.design.md`
- **Fecha:** 2026-10-19
- **Pregunta:** ¿Se integra `codegraph` como servidor de grafo?
- **Opciones:** sustituir `codebase-memory` · añadirlo en paralelo · no integrarlo
- **Decisión:** no integrarlo; queda documentado en `docs/CODE-GRAPH-OPTIONS.md`
- **Fecha:** 2026-10-19
- **Pregunta:** ¿El tamaño de la tarea se sigue midiendo por número de archivos?
- **Opciones:** mantener el conteo · medir por riesgo y comprensión
- **Decisión:** riesgo y comprensión (ADR-008), con motivos de delegación y umbrales
- **Fecha:** 2026-10-19

## Registro de Bloqueos
- Ninguno. `semgrep` no está instalado en este entorno: `aos scan` corre en `--dry-run` (exit 0) y
  `aos doctor` lo reporta como `info`, que es el comportamiento previsto.
