---
id: 202610061905
type: plan
status: active
priority: high
tags: [plan/feature]
created: 2026-10-06
---

# Plan: Feature — generador nativo por herramienta (`aos adapt-native <tool>`)

> Objetivo (Definition of Done): `aos adapt-native claude-code` y `aos adapt-native antigravity` generan de forma determinista e idempotente los nativos de cada herramienta desde `.aos/` (ADR-005), con una clase base común y un adaptador por herramienta. Con tests por adaptador. Prueba real en ambas herramientas: Claude Code con subagentes, skills, hook `SessionStart` y MCP de usuario; Antigravity con skills, regla de roles, hook `PreInvocation` que refresca una vez por conversación y MCP global. La skill `adapt-native` queda como respaldo para herramientas sin adaptador.

## Contexto y Archivos Afectados
- Origen: Fase 12 del plan 002. La prueba real de la skill falló en Antigravity (vocabulario neutral en `tools`, nombres inventados, subagentes en archivo que no se cargan, "al día" sin regenerar). Ver ADR-005.
- Diseño: paquete `dass_aos/native/`. Cada módulo tiene una sola responsabilidad, y las herramientas no saben nada de E/S ni de `.gitignore`.
  ```
  dass_aos/native/
  ├── __init__.py     # registro ADAPTERS = {"claude-code": ClaudeAdapter, "antigravity": AntigravityAdapter} + get_adapter(tool)
  ├── base.py         # NativeAdapter: orquesta run(dry_run, yes) → lista de cambios; define lo que cada herramienta implementa
  ├── sources.py      # lee .aos/ renderizado → Role, Skill, McpServer (dataclasses); reutiliza render_engine_doc y skill_applies
  ├── files.py        # escritura segura: marcador, no tocar sin marcador, merge JSON, bloque .gitignore por herramienta, borrado de obsoletos
  ├── manifest.py     # .aos/native/<tool>.json, source_hash y native_status (movidos desde sync.py)
  ├── claude.py       # ClaudeAdapter(NativeAdapter)
  └── antigravity.py  # AntigravityAdapter(NativeAdapter) + handler de `refresh --hook antigravity`
  ```
  - Cada adaptador declara `TOOL`, `VERIFIED = {version, date, sources}`, sus rutas, el mapeo de `tools_allowed`, el hook y la detección de MCP de usuario. No hace E/S directa: devuelve lo que quiere generar y la base lo escribe a través de `files.py`.
  - Añadir una herramienta = un módulo nuevo + una línea en `ADAPTERS`. Añadir un tipo de artefacto común (por ejemplo, permisos) = un método en la base y su implementación en cada adaptador.
- Archivos previstos: `dass_aos/native/*` (arriba), `dass_aos/cli.py`, `dass_aos/memory.py` (`refresh --hook`), `dass_aos/sync.py` (bloque gestionado y mensaje DESACTUALIZADO), `dass_aos/bootstrap.py` (`CODEBASE_MEMORY_DB`), `dass_aos/templates/skills/specs/adapt-native.md`, `tests/test_native_claude.py`, `tests/test_native_antigravity.py`, `README.md`.
- ADRs vinculados: ADR-004 (parcialmente supersedido), ADR-005.
- Gotchas a considerar: `claude-code-tools-allowlist.md`, `antigravity-subagents-tools-mcp.md` (incorrecto, se reescribe en la Fase 6), `windows-cp1252-encoding.md`.
- Referencia: el script `gen.py` de la sesión del 2026-10-06 ya generó Claude Code correctamente. Es la base del adaptador.
- Fuera de alcance: adaptadores para Codex, Cursor, OpenCode o Gemini CLI (siguen con la skill); `aos init` ejecutando el generador automáticamente.

## Fases de Ejecución Atómica
- [x] Fase 1: Paquete `dass_aos/native/` (`__init__`, `base`, `sources`, `files`, `manifest`) + CLI.
  - Mover `native_source_hash` y `native_status` de `sync.py` a `native/manifest.py` (`sync.py` y `memory.py` los importan desde ahí; `tests/test_native.py` sigue pasando).
  - `sources.py`: `Role(name, description, tools_allowed, body)`, `Skill(name, description, body)` (solo las que aplican, sin `adapt-native`) y `McpServer(name, spec)`.
  - `files.py`:
    - `write_generated(path, text)`: no toca archivos sin marcador y avisa.
    - `merge_json(path, keypath, value)`: la parte sensible, que requiere `--yes`.
    - Borra los archivos del manifiesto anterior que ya no se generan.
    - El bloque `.gitignore` es `# >>> DASS-AOS adapt-native: <tool> …` y solo se reemplaza el suyo.
  - `manifest.py`: el manifiesto lleva `tool`, `tool_version`, `generated_at`, `sources`, `files`, `enforcement`, `mcp` y `source_hash`.
  - `base.py`: `NativeAdapter.run(dry_run, yes)` → lista de cambios. Los métodos que implementa cada adaptador son `agents()`, `skills()`, `rules()`, `hooks()` y `mcp()`; los que no apliquen devuelven vacío.
  - `aos adapt-native <tool> [--dry-run] [--yes]`. Una herramienta desconocida da un error que lista las soportadas y remite a la skill.
  - Tests con un adaptador falso y tmpdir:
    - idempotencia: la segunda ejecución no produce cambios;
    - no toca un archivo sin marcador;
    - borra un generado obsoleto;
    - conserva los bloques de `.gitignore` de otra herramienta;
    - sin `--yes` no escribe la parte sensible;
    - con `--dry-run` no escribe nada.
- [x] Fase 2: `ClaudeAdapter`.
  - `.claude/agents/<rol>.md` con `name`, `description` y `tools`.
    - Mapeo: read→Read; search→Grep, Glob; edit→Edit; write→Write; shell→Bash, PowerShell; web→WebFetch, WebSearch; `mcp:<x>`→nombre registrado.
    - `shell:<prefijo>` se escribe como texto en el cuerpo y el manifiesto lo registra como `shell_prefix: convention`.
  - `.claude/skills/<x>/SKILL.md` para las skills que aplican, sin `adapt-native`.
  - Hook `SessionStart` en `.claude/settings.local.json` (merge).
  - MCP: detectar en la configuración de usuario (`~/.claude.json` `mcpServers` y plugins habilitados en `~/.claude/settings.json`) cómo se llama cada servidor de `.aos/mcp-config.json`. Si falta, avisar y registrar `convention`.
  - Antes, verificar con context7/web el formato y las rutas de configuración de usuario.
  - Tests:
    - nunca aparece vocabulario neutral en `tools`;
    - un rol con `mcp:` incluye `mcp__…`;
    - el hook se fusiona conservando las claves ajenas;
    - la salida coincide con lo que generó `gen.py`.
- [x] Fase 3: `aos refresh --hook antigravity`.
  - Lee el JSON de stdin. La primera vez que ve un `conversationId` imprime `{"injectSteps":[{"ephemeralMessage": <refresco>}]}` y guarda el id en `.aos/native/` (por ejemplo `antigravity-seen.txt`, recortado a los últimos N). Si lo ha visto, o ante cualquier error, imprime `{}`.
  - Nunca falla y la salida es UTF-8.
  - Tests:
    - primer id → inyecta;
    - mismo id → `{}`;
    - stdin inválido → `{}`.
- [x] Fase 4: `AntigravityAdapter`.
  - `.agents/skills/<x>/SKILL.md`.
  - `.agents/rules/dass-aos-roles.md` (breve y con marcador): roles con su `description`, la indicación de delegar con `define_subagent` usando `.aos/agents/<rol>.md` como prompt, y `enable_write_tools: false` si el rol no tiene `edit`/`write`.
  - `.agents/hooks.json` con el hook `dass-aos-refresh`, `PreInvocation` y `cd .. && (aos refresh --hook antigravity || python -m dass_aos refresh --hook antigravity)` (cwd = `.agents/`, `cmd /c`). Se hace merge con los hooks ajenos.
  - MCP: detectar en `~/.gemini/config/mcp_config.json`. No se genera `.agents/mcp_config.json`.
  - Limpieza de lo que dejó la skill: `.agents/agents/*.md` y `.agents/mcp_config.json` solo si tienen marcador o figuran en el manifiesto; si no, se avisa.
  - Manifiesto: `enforcement = {tools: convention, session_start: native-emulated, mcp: user-level}`.
  - Antes, verificar el frontmatter de `.agents/rules/*.md` en la documentación local.
  - Tests:
    - no se generan subagentes en archivo;
    - el hook se fusiona conservando los ajenos;
    - la regla lista todos los roles del motor (7 tras el plan 004) con el flag correcto.
- [x] Fase 5: Integración.
  - Bloque gestionado (`sync.py`): "si `aos refresh` marca DESACTUALIZADO tu herramienta, ejecuta `aos adapt-native <tool>`; si no tiene adaptador, la skill `adapt-native`".
  - `native_status` sugiere el comando cuando la herramienta tiene adaptador.
  - La skill `adapt-native.md` (template y `.aos/`) empieza remitiendo al comando para `claude-code` y `antigravity`.
  - Sale del plan 002 la subtarea de conformidad de `aos refresh`: con el generador no hace falta para las herramientas con adaptador.
  - Tests: el bloque y el mensaje incluyen el comando.
- [ ] Fase 6: Prueba real y gotchas. (Claude Code y gotchas hechos; queda la sesión manual de Antigravity, ver Bloqueos)
  - Claude Code:
    - `aos adapt-native claude-code` → subagentes visibles con las herramientas limitadas;
    - el hook ejecuta `aos refresh` en sesión nueva;
    - `git status` limpio;
    - la segunda ejecución no produce cambios.
  - Antigravity:
    - en sesión nueva, el refresco aparece una sola vez;
    - comprobar si el `ephemeralMessage` sigue disponible en turnos posteriores (si no, valorar `userMessage`);
    - el agente delega con `define_subagent` siguiendo la regla;
    - MCP global disponible.
  - Gotchas:
    - reescribir `antigravity-subagents-tools-mcp.md`: sin subagentes en archivo, `grep_search` no existe, MCP global, `PreInvocation` y JSON;
    - actualizar `claude-code-tools-allowlist.md` si hace falta.
- [x] Fase 7: `CODEBASE_MEMORY_DB`. Confirmar que ninguna herramienta lo aplica (ambas reutilizan el servidor de usuario). Si se confirma, `aos init` deja de escribir la ruta absoluta en `.aos/mcp-config.json`, lo que cierra el riesgo de portabilidad del plan 002. Indexar el repo con `index_repository` y documentar en el README que codebase-memory indexa por proyecto en la DB del usuario. Tests de bootstrap actualizados.
- [x] Fase 8: Cierre.
  - `aos verify` y `aos scan --dry-run`.
  - README: el comando, las herramientas soportadas, la skill de respaldo y qué es nativo y qué convención por herramienta.
  - Se suma a la versión 0.6.0 del plan 002.
  - Archivar el plan.

## Registro de Preguntas y Decisiones (Discovery Trail)
- **Pregunta:** ¿Partir la skill en `adapt-native-claude.md` y `adapt-native-antigravity.md`, o un comando?
- **Opciones:** (a) dos specs por herramienta; (b) `aos adapt-native --antigravity`; (c) `aos adapt-native <tool>` con clase base y un adaptador por herramienta.
- **Decisión:** (c). El autor pidió una clase base de la que hereden `claude.py` y `antigravity.py`, todo dentro de la carpeta `dass_aos/native/` y modularizado para poder añadir herramientas y tipos de artefacto sin desorden. El argumento es posicional para que escale. La skill se mantiene como respaldo.
- **Fecha:** 2026-10-06

- **Fecha:** 2026-10-16 · Ejecución (tras el plan 004):
  - **Claude Code** (verificado en code.claude.com/docs: sub-agents, hooks, skills):
    - `tools` es allowlist y deja fuera los MCP; `disallowedTools` quita solo lo que nombra. Por eso el adaptador bloquea lo que le falta al rol (p. ej. `reviewer` → `Edit, NotebookEdit, Write, WebFetch, WebSearch`) y los MCP se heredan.
    - La detección de MCP de usuario queda solo para el manifiesto y el aviso.
    - Patrón tomado de `cms-crai/.aos/skills/bin/adapt_native_claude.py`. `gen.py` ya no existía.
    - Enmienda en ADR-005 §4.
  - **Antigravity:** la documentación local solo documenta reglas en `GEMINI.md`/`AGENTS.md` y plugins.
    - No se genera `.agents/rules/*.md`.
    - La delegación con `define_subagent` y la lista de roles sin escritura van en el bloque gestionado de `GEMINI.md` (`sync.antigravity_delegation`, con test).
    - Enmienda en ADR-005 §7.
  - **`CODEBASE_MEMORY_DB`:** ninguna herramienta lo aplica, porque las dos reutilizan el servidor de usuario.
    - `aos init` ya no escribe la ruta absoluta.
    - Se quita `.aos/memory/` y su informe en `aos refresh`.
    - Repo indexado con `index_repository`: 950 nodos.
- **Fecha:** 2026-10-16 · Prueba real en este repo:
  - `aos adapt-native claude-code --yes` y `antigravity --yes` regeneran 19 cambios cada uno.
    - En Antigravity, borra los subagentes en archivo que dejó la skill.
    - La segunda ejecución da "al día, sin cambios".
    - `git status` no muestra lo generado.
  - Claude Code, en la misma sesión:
    - aparecen como skills nativas `adversarial-review`, `live-verify` y `phased-delivery`;
    - aparece el subagente `adversarial-verifier`, que después se usó para verificar los hallazgos de este plan.
  - Instalación limpia en un venv: el wheel incluye `dass_aos/native/` y las plantillas nuevas; `init` → `adapt-native` ×2 idempotente → hook.
  - Hook de Antigravity probado como lo ejecuta Antigravity (`cmd /c` desde `.agents/`):
    - Falló primero porque stdin llegaba con BOM y en cp1252.
    - Corregido: lectura de bytes con `utf-8-sig`, con test visto fallar.
    - Tras la corrección, la primera llamada inyecta el refresco y la segunda devuelve `{}`.
- **Fecha:** 2026-10-16 · `adversarial-review` del plan:
  - Dos lentes (correctitud y seguridad): 13 hallazgos. Verificados con el subagente nativo `adversarial-verifier`: 12 confirmados y E4 confirmado con la causa corregida.
  - Corregidos todos con test:
    - A1/A4: borrado y escritura confinados al proyecto (`confined`: sin `..`, rutas absolutas ni symlinks).
    - A2: nunca se borra un JSON sin marcador; se avisa REVISAR.
    - A3: comparación por ruta resuelta.
    - B1: un grupo SessionStart mixto conserva los hooks del usuario.
    - B2: JSON con BOM se fusiona; JSON ilegible se omite con aviso, sin abortar.
    - B3: se conserva `enabled: false`.
    - B4: un hook pendiente sigue en el manifiesto y en `.gitignore`.
    - E1: un marcador de inicio sin cierre deja `.gitignore` intacto.
    - E2: frontmatter con BOM o sin salto final.
    - E3: `tools_allowed` en YAML de bloque falla con error (`validate_tools_allowed` al inicio de `run`).
    - E4: clave de proyecto en `~/.claude.json` con cualquier grafía.
  - `aos verify`: 59 tests. `aos scan --dry-run`: OK.

## Registro de Bloqueos
- Fase 6, solo la parte manual en Antigravity: abrir una conversación nueva en este repo y comprobar:
  - que el refresco aparece una sola vez;
  - si el `ephemeralMessage` sigue visible en turnos posteriores (si no, valorar `userMessage`);
  - que el agente delega con `define_subagent` siguiendo el bloque de `GEMINI.md`.
  - Falta context7 en `~/.gemini/config/mcp_config.json`: el generador lo avisa.
