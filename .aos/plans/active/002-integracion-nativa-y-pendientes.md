---
id: 202610051730
type: plan
status: active
priority: medium
tags: [plan/feature, plan/meta]
created: 2026-10-05
updated: 2026-10-06
---

# Plan: Feature — dependencias externas, adaptación nativa delegada y pendientes de 0.5.0

> Objetivo (Definition of Done): (1) las dependencias externas del framework (codebase-memory, context7, Semgrep, Checkov) quedan declaradas en `.aos/`, instalables y diagnosticadas, y Checkov solo actúa cuando el proyecto tiene IaC; (2) cualquier herramienta de IA (Claude Code, Antigravity, Codex, Cursor, OpenCode, Gemini…) que abra un proyecto con DASS-AOS recibe, vía el bloque gestionado, la orden de ejecutar la skill `adapt-native`, que genera **sus** formatos nativos (subagentes, skills, hooks, MCP, restricciones de herramientas) a partir de `.aos/`, consultando la documentación actual de esa herramienta. El motor no mantiene generadores por proveedor. `.aos/` sigue siendo la única fuente de verdad (ADR-002/003).

## Contexto
- Origen: pendientes del plan archivado `001-portabilidad-y-adaptacion.md` + revisión del 2026-10-06.
- Problema: `hooks/*.md` y `tools_allowed` son solo texto; un generador por proveedor no escala y se queda obsoleto. Las dependencias externas están implícitas: `mcp-config.json` solo declara codebase-memory (+ un `filesystem` redundante), context7 no aparece, y `aos scan` intenta Checkov aunque no haya IaC.
- Enfoque: la adaptación la hace el agente de cada herramienta (conoce su entorno y lee su documentación actual). El motor garantiza el contrato (vocabulario, `mcp-config.json`), la trazabilidad (manifiesto) y la detección de desincronización (hash).
- Decisiones del autor (2026-10-06): solo skill (sin rol nuevo); los artefactos nativos generados **se ignoran en git** y cada dev ejecuta `adapt-native`; herramientas de prueba: Claude Code + Antigravity.
- Usuarios actuales: solo el autor. Sin migración de 0.4.0 que soportar.
- Archivos previstos: `dass_aos/bootstrap.py`, `dass_aos/scanners.py`, `dass_aos/sync.py`, `dass_aos/memory.py` (refresh), `dass_aos/cli.py`, `pyproject.toml`, `dass_aos/templates/agents/*.md`, `dass_aos/templates/skills/specs/*.md` (+ `adapt-native.md`), `tests/`, `README.md`.
- ADRs vinculados: ADR-002, ADR-003. Nuevo ADR-004 en Fase 2.
- Fuera de alcance: `LICENSE`; `aos sync --reset-engine-docs` (sin usuarios de 0.4.0); generadores nativos por proveedor en Python; rol `integrator`.

## Fases

### Bloque A — Pendiente de 0.5.0
- [x] Fase 1: Reemplazar `.git/hooks/pre-commit` de este repo (todavía `python aos.py verify || exit 1`) por `GIT_PRE_COMMIT` de `dass_aos/bootstrap.py`. Una línea en el README: `aos init` no pisa un hook existente; reemplazarlo a mano.

### Bloque B — Decisión y contrato
- [x] Fase 2: ADR-004 "Adaptación nativa delegada en el agente". Registrar: el motor no genera formatos por proveedor; `adapt-native` los genera; manifiesto + hash para desincronización; marcador obligatorio en todo lo generado; aprobación humana para hooks/permisos; **artefactos nativos ignorados en git** (cada dev ejecuta `adapt-native`; `adapt-native` añade sus rutas generadas a un bloque marcado de `.gitignore`, sin ignorar carpetas enteras como `.claude/` que pueden tener archivos del usuario). Verificar con context7 (y web si no hay certeza) si `SKILL.md` es un estándar compartido entre herramientas y qué rutas usa cada una; si lo es, anotarlo como atajo en la skill.
- [x] Fase 3: Vocabulario neutral de `tools_allowed` (p. ej. `read`, `search`, `edit`, `write`, `shell:<cmd>`, `skill:<nombre>`, `mcp:<servidor>`). `mcp:` es necesario porque restringir herramientas en Claude Code excluye las MCP no listadas y el ciclo de vida exige `codebase-memory`. Evaluar lista de bloqueo (`tools_denied`) si es más simple para casos como reviewer (sin `edit`/`write`). Registrar en ADR-004. Migrar los 6 roles. `aos sync` falla con mensaje claro ante un valor desconocido. Test: valor inválido → error; roles del motor → válidos.
- [x] Fase 4: Metadatos para delegación. `description:` de una línea en cada `agents/*.md` (derivada de "Misión"/"Cuándo asumirlo") y en las skill specs que no lo tienen (api-smoke-test, bootstrap-project, checkov-scan, db-migration-check, sync-agent-instructions). Test: todo template de agente/skill tiene nombre y `description`.

### Bloque C — Dependencias externas
- [x] Fase 5: MCP declarados en `.aos/mcp-config.json` como fuente neutral (la traduce `adapt-native` al formato de cada herramienta). `aos init` genera `codebase-memory` y **`context7`** (comando/URL confirmados con context7 o web). `filesystem` ya eliminado el 2026-10-06. Test: bootstrap genera ambos servidores.
- [x] Fase 6: Checkov condicional. Añadir `applies_when` con globs de IaC a `checkov-scan.md` (Terraform `*.tf`, `Dockerfile`, `docker-compose*.yml`, `k8s/`, `helm/`/`Chart.yaml`, CloudFormation, `.github/workflows`… lista final confirmada contra los frameworks que soporta Checkov). `aos scan` (sin `--tool`) reutiliza `skill_applies` y omite Checkov con un mensaje cuando no aplica; `--tool checkov` explícito lo ejecuta igual. Semgrep sigue siendo general. Test con tmpdir: sin IaC → Checkov omitido; con `main.tf` → incluido.
- [x] Fase 7: Instalación. Extra opcional en `pyproject.toml`: `pip install dass-aos[scan]` → semgrep + checkov (no obligatorios: el núcleo sigue sin dependencias). Verificar con context7/web el soporte de Semgrep en Windows nativo y documentar la alternativa si no hay (WSL/Docker). codebase-memory y context7 no son pip: README con cómo instalarlos.
- [x] Fase 8: Diagnóstico en `aos refresh`: listar dependencias externas que faltan **solo si aplican** (semgrep siempre, checkov solo con IaC, `codebase-memory-mcp` en PATH, `npx`/node si context7 lo requiere), con la pista de instalación. Nunca falla, solo avisa. Test: PATH sin herramientas → avisos esperados; proyecto sin IaC → sin aviso de checkov.

### Bloque D — Adaptación delegada
- [x] Fase 9: Skill spec `adapt-native.md` (instrucciones para el agente, sin código por proveedor):
  1. Identificar la herramienta en la que corre y su versión si es posible.
  2. Consultar el formato nativo actual **primero con context7**; si context7 no lo cubre o hay cualquier duda, **buscar en la web** la documentación oficial. Nunca escribir formatos de memoria. Citar las fuentes en el manifiesto.
  3. Generar desde `.aos/` renderizado (base + `.local.md`): subagentes por rol, skills que aplican (`applies_when`), servidores MCP de `.aos/mcp-config.json`, hook de inicio de sesión que ejecute `aos refresh` (fallback `python -m dass_aos refresh`, nunca bloqueante, sin depender del PATH) y traducción de `tools_allowed` según el vocabulario de la Fase 3.
  4. Reglas: marcador `DASS-AOS-GENERATED` en todo archivo generado (después del frontmatter si el formato lo exige; en JSON/TOML, identificar por nombre de servidor/comando); nunca tocar archivos sin marcador; merge de configuración sin pisar la del usuario; borrar solo generados que ya no corresponden.
  5. Si la herramienta no soporta restringir herramientas, dejar la restricción como texto en el rol y anotarlo en el manifiesto (`enforcement: convention`).
  6. Añadir las rutas generadas al bloque marcado de `.gitignore`.
  7. Mostrar el diff y pedir aprobación humana antes de escribir hooks, permisos o MCP.
  8. Escribir el manifiesto (Fase 10).
- [x] Fase 10: Manifiesto y desincronización (código determinista). `.aos/native/<herramienta>.json` (local, ignorado en git) con: herramienta, fecha, fuentes consultadas, archivos generados, `enforcement` (`native` | `convention`) y `source_hash` (hash de `agents/`, `skills/specs/`, `hooks/` y `mcp-config.json` renderizados). `aos init` añade `.aos/native/` a `.gitignore`. `aos sync` y `aos refresh` recalculan el hash y, si difiere, avisan: "fuentes cambiadas → ejecutar adapt-native en <herramienta>". Test con tmpdir: manifiesto al día → sin aviso; modificar un rol → aviso.
- [x] Fase 11: Bloque gestionado. Añadir a CLAUDE.md/AGENTS.md/GEMINI.md/etc.: "si no existe `.aos/native/<tu-herramienta>.json` o `aos refresh` avisa de desincronización, ejecuta la skill `adapt-native`". Ajustar el paso 1 del ciclo de vida: donde haya hook nativo, `aos refresh` ya es automático. Test: el bloque generado contiene la instrucción.

### Bloque E — Cierre
- [ ] Fase 12: Verificación: `aos verify`, `aos scan --dry-run`, instalación limpia (`pip install .` y `pip install .[scan]` en venv) → `aos init`. Prueba real de `adapt-native` en **Claude Code** y **Antigravity**: se generan los nativos (incluidos MCP codebase-memory y context7), el hook ejecuta `aos refresh` al iniciar sesión, los subagentes aparecen con herramientas limitadas donde se soporta, `git status` no muestra lo generado, el manifiesto es correcto y una segunda ejecución es idempotente. Anotar lo aprendido como gotchas.
- [ ] Fase 13: README (dependencias externas y cómo instalarlas, adaptación delegada, qué es nativo y qué convención según el manifiesto), archivar el plan, versión 0.6.0.

## Discovery Trail / Bloqueos
- 2026-10-05: Plan creado a partir de los pendientes del plan 001.
- 2026-10-06: Revisión. Se descarta generar formatos nativos por proveedor en el motor; se delega en la skill `adapt-native` con context7 + web como fuentes obligatorias. Se descarta `--reset-engine-docs`. Riesgos: restringir `tools` en Claude Code excluye MCP no listadas (→ `mcp:`); `aos` puede no estar en el PATH del hook (→ fallback `python -m`); `aos init` no puede ordenar nada al agente (→ la orden va en el bloque gestionado).
- 2026-10-06: Decisiones del autor: solo skill; nativos ignorados en git; prueba en Claude Code + Antigravity. Se añade el bloque de dependencias externas (codebase-memory, context7, Semgrep general, Checkov solo con IaC).
- 2026-10-06: Eliminado el MCP `filesystem` (duplicaba herramientas nativas y no busca por contenido). Si la documentación de `.aos/` crece y cuesta saber qué leer: que `aos refresh` genere `.aos/INDEX.md` (ruta + título + tags por documento). No antes de necesitarlo.
- 2026-10-06: Fase 12 (parte automática) OK: venv limpio → `pip install .` y `.[scan]` → `aos init` (gitignore `.aos/native/`, MCP codebase-memory + context7) → `aos refresh` → `aos scan` real. Semgrep corre en Windows nativo con `PYTHONUTF8=1`. Corregido: escáneres no encontrados en venv no activado y `checkov.cmd` usando el Python global (gotcha `escaneres-en-venv-no-activado.md`). Pendiente manual: `adapt-native` en Claude Code y Antigravity.
- 2026-10-06: Semgrep real reporta en templates del motor: `ci/github-actions/security.yml` con tags mutables (`actions/checkout@v4`, fijar SHA) y `skills/bin/run_smoke_test.py:19` urllib con URL dinámica (restringir a http/https). Fuera de alcance de este plan; candidato a plan `security`.
- 2026-10-06: Riesgo abierto: `aos init` escribe en `.aos/mcp-config.json` (versionado) la ruta absoluta de la DB de codebase-memory; no es portable entre devs.
