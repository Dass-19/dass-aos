---
id: 202611161043
type: trd
status: approved
tags: [spec/trd, tui, textual, telemetry]
created: 2026-11-16
prd: 002-tui-de-monitoreo-en-tiempo-real.prd.md
---

# TRD: TUI de monitoreo en tiempo real

> Cómo se construye y por qué así. **No repite el PRD: lo cita.**

## Contexto
- **PRD**: `002-tui-de-monitoreo-en-tiempo-real.prd.md` — cubre `CA-1`..`CA-7`.
- **Componentes previstos**:
  - `dass_aos/telemetry.py` (nuevo, stdlib pura Python >=3.8): recolección de estado `.aos/`, Git, sesiones/tareas de Claude Code y Antigravity, y generación de eventos delta entre snapshots.
  - `dass_aos/tui/__init__.py` (nuevo): punto de entrada con importación perezosa de `textual` y manejo de dependencia faltante (`CA-1`).
  - `dass_aos/tui/app.py` (nuevo): aplicación Textual (`AosTuiApp`), workers de refresco y ejecución de comandos, bindings y pestañas (`CA-4`, `CA-5`, `CA-6`).
  - `dass_aos/tui/widgets.py` (nuevo): widgets/paneles reutilizables (tarjetas de estado, árbol/tabla de fases, panel de agentes/tasks, visor de log/diff, buscador RAG).
  - `dass_aos/tui/styles.tcss` (nuevo): hoja de estilos Textual empaquetada junto a `dass_aos/tui/`.
  - `dass_aos/cli.py`: subcomando `aos tui` (`--project-root`, `--interval`).
  - `pyproject.toml`: extra opcional `tui = ["textual>=0.70"]` y `package-data` incluyendo `tui/*.tcss`.
  - `tests/test_telemetry.py` (nuevo) y `tests/test_tui.py` (nuevo).

## Arquitectura y límites
- **Componentes tocados**: CLI (`cli.py`), empaquetado (`pyproject.toml`), nuevo módulo `telemetry.py`, nuevo subpaquete `tui/`. Reutiliza sin duplicar lógica: `status.build_report`, `doctor.collect_findings`, `specs.open_specs`, `memory.list_recent_gotchas`, `memory.list_recent_lessons`, `memory.missing_dependencies`, `native.manifest.native_status` y `rag.search_context`.
- **Fronteras**:
  - `dass_aos/telemetry.py` **no** importa `textual` ni escribe en el sistema de archivos (100% read-only sobre `.aos/`, Git, `~/.claude/` y `~/.gemini/antigravity/`).
  - Los directorios de sesión de herramientas (`claude_home`, `antigravity_home`) se reciben como parámetros opcionales (por defecto `Path.home() / ".claude"` y `Path.home() / ".gemini" / "antigravity"`), permitiendo pruebas deterministas sin tocar `$HOME`.
  - Las lecturas de archivos potencialmente grandes (`transcript.jsonl`, `*.log`, `git diff`) aplican límites de cola/tamaño en bytes/líneas para evitar picos de memoria en cada tick de refresco.
  - Los subprocesos disparados desde la TUI (`aos verify`, `aos scan`, `aos sync`, `aos refresh`) se ejecutan vía `subprocess.Popen` con `PYTHONUTF8=1` / UTF-8 en workers de Textual para evitar bloqueos y errores `cp1252` en Windows.

## Contratos
- **HTTP / Eventos**: sin cambios (herramienta CLI/TUI local).
- **Esquemas / tipos internos (`dass_aos/telemetry.py`)**:
  - `PhaseItem(done: bool, text: str, details: list[str])`
  - `PlanDetail(path: Path, title: str, status: str, total: int, done: int, phases: list[PhaseItem], unanswered_questions: int, raw_markdown: str)`
  - `GitFileChange(code: str, path: str)` y `GitSnapshot(available: bool, branch: str, clean: bool, changes: list[GitFileChange], diff_stat: str, recent_commits: list[str])`
  - `AgentTaskInfo(id: str, agent: str, status: str, log_path: Optional[Path], updated_at: float, tail_lines: list[str])`
  - `AgentActivityItem(timestamp: str, agent: str, kind: str, summary: str)`
  - `AgentSessionInfo(tool: str, session_id: str, title: str, status: str, cwd: str, updated_at: float, subagents: list[str], recent_tools: list[str], tasks: list[AgentTaskInfo], activities: list[AgentActivityItem])`
  - `TelemetrySnapshot(timestamp: float, project_root: Path, status_report: StatusReport, active_plans: list[PlanDetail], archived_plan_names: list[str], specs: list[SpecEntry], gotchas: list[dict], lessons: list[str], native_tools: dict[str, str], missing_deps: list[tuple[str, str]], doctor_findings: list[Finding], git: GitSnapshot, sessions: list[AgentSessionInfo], tasks: list[AgentTaskInfo])`
  - `LiveEvent(timestamp: str, level: str, source: str, message: str)` producido por `diff_snapshots(prev, curr)`.

## Modelo de datos y fuentes locales observadas
- **Claude Code (`~/.claude/`)**:
  - `~/.claude/sessions/*.json`: JSON por sesión con `pid`, `sessionId`, `cwd`, `startedAt`, `status`, `updatedAt`, `name`, `entrypoint`. Se filtra normalizando rutas (`Path(cwd).resolve() == project_root.resolve()`).
  - `~/.claude/projects/<encoded-cwd>/*.jsonl`: eventos en líneas JSONL (`type`, `timestamp`, `cwd`, `sessionId`, bloques `tool_use` / contenido reciente). Se leen únicamente los últimos KB del archivo más reciente por sesión.
  - `~/.claude/tasks/`: tareas asociadas si existen archivos JSON/log recientes.
- **Antigravity (`~/.gemini/antigravity/brain/`)**:
  - Correlación con el proyecto: IDs en `.aos/native/antigravity-seen.txt` y detección de rutas del `project_root` en los primeros/últimos bloques de `.system_generated/logs/transcript.jsonl` (tolerando rutas Windows `C:\...` o JSON-escapadas `C:\\...`).
  - `transcript.jsonl`: última secuencia de pasos (`step_index`, `source`, `type`, `status`, `created_at`, `tool_calls` incluyendo `name`, `Role`/`TypeName` en `invoke_subagent`, `Path`/`CommandLine` resumidos).
  - `.system_generated/tasks/*.log`: archivos de log de tareas en background, con lectura de las últimas N líneas (`tail`) y estado inferido por actividad/mtime reciente.
- **Tolerancia a concurrencia**:
  - Cada línea JSONL que falle `json.loads` (por escritura parcial en curso) se ignora silenciosamente sin abortar el resto del archivo.
  - `OSError` / `PermissionError` / `UnicodeDecodeError` en archivos de terceros nunca rompen el snapshot; devuelven sesión parcial o advertencia no fatal.

## Decisiones
- ADRs vinculados: `ADR-010-tui-opcional-textual-y-telemetria-local.md`

## Dependencias nuevas
- Extra opcional en `pyproject.toml`: `tui = ["textual>=0.70"]` (aprobado en `ADR-010`).
- Nota de compatibilidad: `textual` requiere Python `>=3.9`. El núcleo `dass-aos` y `dass_aos/telemetry.py` conservan compatibilidad con Python `>=3.8` para no romper la matriz de CI ni entornos sin `[tui]`.

## Plan de prueba
- **Unitarias (`tests/test_telemetry.py`)** — corren en Python 3.8–3.12 sin `[tui]`:
  - Recolección completa de `.aos/` (planes con fases, preguntas abiertas, specs, gotchas, lecciones, doctor).
  - Parsers de Claude Code y Antigravity con `tmp_path` simulando sesiones de este proyecto y de otros proyectos (filtrado por `project_root`), JSONL truncado y logs de tareas en background (`CA-3`).
  - `diff_snapshots(prev, curr)` detectando fases completadas, cambios de estado, nuevos archivos Git y nuevas tareas/pasos de agente (`CA-2`, `CA-5`).
  - Comportamiento de `aos tui` cuando `textual` no está instalado (`CA-1`).
- **Tests de TUI (`tests/test_tui.py`)**:
  - Pruebas asíncronas con `app.run_test()` (Textual Pilot), saltadas limpiamente con `skipUnless` si `textual` no está instalado: montaje inicial, cambio entre pestañas (`1`..`6`), filtro de búsqueda `aos context`, y disparo de acción en background (`CA-4`, `CA-5`, `CA-6`).
- **Verificación en vivo (`live-verify`)**:
  - Instalar/verificar `textual` en el entorno local (`pip install -e ".[tui]"`), lanzar `python -m dass_aos tui` sobre `dass-aos`, ejercitar navegación, búsqueda RAG, visor de diff/agentes y ejecución de `verify`/`sync`, capturando evidencia y comprobando cero excepciones y salida limpia con `q`.

## Observabilidad
- La propia TUI muestra en su barra de estado/footer el estado del colector, timestamp del último snapshot, duración del ciclo de muestreo y errores no fatales en el feed de eventos.
- Los comandos ejecutados en el runner registran código de salida, duración y salida completa en la vista Consola.

## Riesgos técnicos
- **Bloqueo del loop de eventos en Windows**: ejecutar `git` o subprocesos `aos` síncronos en el hilo principal congelaría la TUI. Mitigación: todo I/O de snapshot y subprocesos corre en Textual workers (`thread=True`), comunicándose con la UI mediante mensajes/callbacks thread-safe (`call_from_thread`).
- **Consumo excesivo en repositorios grandes o transcripts largos**: mitigado leyendo solo la cola de los archivos (`seek` desde el final) y acotando `git diff` por archivo seleccionado bajo demanda en lugar de precalcular todos los diffs en cada tick.

## Referencias
- **Plan**: `.aos/plans/active/008-tui-de-monitoreo-en-tiempo-real.md`
