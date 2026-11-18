---
id: 202611180838
type: trd
status: approved
tags: [spec/trd, tui, telemetry, sessions, workflows, notifications, tts]
created: 2026-11-18
prd: 003-tui-v2-lazy-loading-workflows-alertas-pending-control-de-sesiones-y-voz.prd.md
---

# TRD: TUI v2: Lazy Loading, Workflows, Alertas Pending, Control de Sesiones y Voz

> Cómo se construye y por qué así. **No repite el PRD: lo cita.**

## Contexto
- **PRD**: `003-tui-v2-lazy-loading-workflows-alertas-pending-control-de-sesiones-y-voz.prd.md` — cubre `CA-1`..`CA-8`.
- **Archivos y componentes previstos**:
  - `dass_aos/telemetry.py`: caché incremental por `(path, mtime_ns, size)`, `started_at`/`updated_at` en `AgentTaskInfo`, mapeo completo de subagentes/tasks/workflows/archivos tocados de Claude Code y Antigravity, y detección de estado `pending` + `pending_reason`.
  - `dass_aos/tui/pty_terminal.py` (nuevo, `ADR-011`): backend PTY multiplataforma (`ConPTY` vía `ctypes.windll.kernel32` con `STARTF_USESTDHANDLES` en Windows y `pty.openpty()` en Unix), emulador de pantalla 2D VT100/TrueColor (`VtScreen`), codificador de teclas de terminal (`encode_terminal_key`) y detector de estado en vivo por pantalla/OSC (`detect_terminal_agent_state` con las reglas de `claude.toml` y `agy.toml`).
  - `dass_aos/tui/controller.py`: gestor de sesiones interactivas estilo Herdr (sesiones PTY vivas en `PtySessionManager` + envío de prompts/teclas, alertas sonoras/OS toast y síntesis TTS sincronizada con `/voice`).
  - `dass_aos/tui/app.py`: renderizado perezoso solo de la pestaña activa (`CA-1`), widget interactivo `AgentTerminalWidget` en la pestaña `3 · Agentes & Tasks` con **Modo Terminal** vs **Modo Navegación** (`Ctrl+G` / `Ctrl+B`), apertura/reanudación de PTY en vivo (`Enter` / botón `Abrir CLI`), alternancia de vista (`Terminal PTY` vs `Inspector`), alertas `pending` y parada de TTS con `Esc`.
  - `dass_aos/tui/widgets.py` y `dass_aos/tui/styles.tcss`: formateo de datetimes `YYYY-MM-DD HH:MM:SS` + duración, badges `PENDING` / `WORKFLOW` / `SUBAGENT`, renderizador topológico `format_subagent_graph` (`CA-8`) y estilos del viewport VT100 interactivo (`min-height: 12`, resumen compacto en modo Terminal/Grafo).
  - `tests/test_telemetry.py` y `tests/test_tui.py`: pruebas unitarias y de Textual Pilot para `CA-1`..`CA-8`.

## Arquitectura y límites
- **Componentes tocados**: `dass_aos/telemetry.py`, `dass_aos/tui/app.py`, `dass_aos/tui/widgets.py`, `dass_aos/tui/styles.tcss`, nuevo `dass_aos/tui/controller.py`, y suites de tests.
- **Fronteras**:
  - `dass_aos/telemetry.py` permanece 100% stdlib pura (Python >=3.8) y de solo lectura sobre el sistema de archivos; toda acción con efectos secundarios (lanzar/reanudar un agente, enviar un prompt, reproducir sonido, mostrar toast del SO o hablar por TTS) vive aislada en `dass_aos/tui/controller.py`.
  - No se añaden dependencias externas obligatorias: las notificaciones del SO y el motor TTS usan APIs nativas del sistema operativo (`winsound` + PowerShell `System.Speech.Synthesis` / Toast en Windows, `afplay`/`say`/`osascript` en macOS, `spd-say`/`espeak`/`notify-send` en Linux) ejecutadas en subprocesos no bloqueantes con degradación limpia si no están disponibles.

## Contratos
- **HTTP / Eventos externos**: sin cambios.
- **Esquemas y tipos internos (`dass_aos/telemetry.py` & `dass_aos/tui/controller.py`)**:
  - `AgentTaskInfo`:
    - Nuevos campos: `started_at: float = 0.0`, `kind: str = "task"` (`"task" | "subagent" | "workflow" | "cron"`), `agent_type: str = ""` (ej. `"reviewer"`, `"Explore"`).
    - Propiedad `duration_seconds -> float`: `max(0.0, (updated_at or time.time()) - started_at)` cuando `started_at > 0`.
  - `AgentSessionInfo`:
    - Nuevos campos:
      - `pending_reason: str = ""` (detalle de la pregunta `AskUserQuestion`/`ask_question`, `ExitPlanMode`, `RequestFeedback` o herramienta esperando permiso).
      - `workflows: List[str] = field(default_factory=list)` (workflows y skills ejecutados en la sesión).
      - `touched_files: List[str] = field(default_factory=list)` (rutas relativas al proyecto extraídas de `file-history-delta`, `Write`, `Edit`, `write_file`, `edit_file`, `replace_file_content`).
      - `voice_active: bool = False` (indica si la sesión tiene `/voice` activo o si el último turno del usuario se originó por voz).
      - `last_assistant_text: str = ""` (última respuesta conversacional limpia del asistente, sin bloques de código, lista para TTS o vista detallada).

## Modelo de datos y fuentes locales observadas
1. **Caché incremental (`_FILE_STAT_CACHE` en `dass_aos/telemetry.py`, `CA-1`)**:
   - Diccionario indexado por ruta resuelta que guarda `(mtime_ns, size, parsed_value)` para:
     - Planes `.aos/plans/active/*.md` (`PlanDetail` sin releer markdown si `mtime_ns` y `size` coinciden).
     - Sesiones JSONL de Claude Code (`~/.claude/projects/<slug>/*.jsonl`) y Antigravity (`~/.gemini/antigravity/brain/<id>/.system_generated/logs/transcript.jsonl`).
     - Subagentes (`<session>/subagents/agent-*.meta.json` + `.jsonl`) y tasks (`.system_generated/tasks/*.log`, `<session>/tool-results/*.txt`, `~/.claude/tasks/<session>/*.json`).
   - En `AosTuiApp._apply_snapshot`, solo se invoca el actualizador de la pestaña activa (`TabbedContent.active`) además del header; se guarda un conjunto `_dirty_tabs: set[str]` y al cambiar de pestaña (`on_tabbed_content_tab_activated` / `action_switch_tab`) se sincroniza la pestaña recién activada al instante.
2. **Mapeo de Workflows, Subagentes, Tasks y Archivos tocados (`CA-2`, `CA-3`)**:
   - **Claude Code**:
     - `<session_id>/subagents/agent-<id>.meta.json` + `.jsonl`: crea `AgentTaskInfo(kind="subagent", agent="claude-code", status="finished" if meta.get("finished") else "running", started_at=first_jsonl_ts_or_ctime, updated_at=last_jsonl_ts_or_mtime, agent_type=meta.get("agentType"), title=meta.get("description"))` y extrae las últimas líneas de actividad/respuesta del subagente como `tail_lines`.
     - `<session_id>/tool-results/*.txt`: crea `AgentTaskInfo(kind="task", started_at=ctime, updated_at=mtime)` con la cola del resultado.
     - Llamadas en `<session_id>.jsonl` a `Workflow` (`input.scriptPath`), `Skill` (`input.skill`), `EnterPlanMode`/`ExitPlanMode`, `CronCreate` (`input.cron`, `input.prompt`) y `Bash`/`PowerShell`/`Agent` con `run_in_background=True`: se registran en `sess.workflows`, `sess.tasks` y `sess.activities` con sus timestamps ISO convertidos a epoch (`started_at`/`updated_at`).
     - Eventos `file-history-delta` (`trackingPath`) + llamadas `Write`/`Edit` (`file_path`): se normalizan respecto a `project_root` y se agregan a `sess.touched_files`.
     - Equipos en `~/.claude/teams/session-<prefix>/config.json`: se asocian a la sesión líder (`leadSessionId`) añadiendo sus miembros a `sess.subagents`.
   - **Antigravity**:
     - `.system_generated/tasks/*.log`: `started_at` desde el primer timestamp detectado en el log o `st_ctime`, y `updated_at` desde `st_mtime`.
     - Llamadas en `transcript.jsonl` a `invoke_subagent` / `define_subagent` / `swarm` y `run_workflow` / `schedule`: se registran como `AgentTaskInfo(kind="subagent" | "workflow" | "cron")` con `started_at` del `created_at` del paso, y en `sess.workflows`.
     - Llamadas `write_file` / `edit_file` / `replace_file_content` / `multi_replace_file_content` / `write_to_file`: rutas relativas en `sess.touched_files`.
3. **Detección de `pending` y alertas multicanal (`CA-4`)**:
   - Una sesión se marca `status = "pending"` cuando:
     - En Claude Code: el último mensaje relevante en el JSONL es `type == "assistant"` con `stop_reason == "tool_use"` sin `tool_result` posterior para ese `tool_use_id`. Si la herramienta es `AskUserQuestion`, `pending_reason` incluye el texto de la pregunta; si es `ExitPlanMode`, indica aprobación de plan; si es otra herramienta (`Bash`, `Edit`, `Write`, etc.) y lleva `>= 2s` sin `tool_result`, indica `Esperando permiso: <tool>`.
     - En Antigravity: el último paso `PLANNER_RESPONSE` invoca `ask_question` o `write_file`/`edit_file` con `ArtifactMetadata.RequestFeedback == True` sin `USER_INPUT` posterior.
   - Cuando `diff_snapshots` o la TUI detecta que una sesión pasa a `status == "pending"`, dispara `AlertDispatcher.notify_pending(session)` (respetando el flag `muted` con tecla `m`): banner en TUI + sonido (`winsound.MessageBeep` / `\a`) + toast nativo del SO en worker asíncrono.
4. **Controlador de sesiones estilo Herdr y puente `/voice` + TTS (`CA-5`, `CA-6`)**:
   - `SessionController` en `dass_aos/tui/controller.py` gestiona sesiones lanzadas o reanudadas desde la pestaña 3:
     - `send_prompt(tool, session_id, name, prompt, voice_mode=False)`: lanza o reanuda la sesión en un proceso hijo (`claude --resume <id> -p "<prompt>" --output-format stream-json --verbose` o sesión nueva con `--session-id <uuid> -n <slug>`), volcando en tiempo real la salida detallada del agente en el visor de la pestaña 3 (`#agents-activity-log` / `#agents-task-log`).
     - `trigger_voice(session)`: activa el modo `/voice` para la sesión (enviando `/voice` al proceso interactivo de Claude o iniciando captura de voz de la sesión) y marca `voice_active = True`.
     - `speak_response(text)` (`TTSManager`): extrae la respuesta conversacional limpia (eliminando bloques ```...```, rutas largas y diffs) y lanza un subproceso asíncrono de síntesis de voz del SO (`powershell -NoProfile -Command "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak(...)"` en Windows, `say` en macOS, `spd-say`/`espeak` en Linux). `stop_speaking()` termina el subproceso inmediatamente al pulsar `Esc` o al enviar un nuevo turno.

## Decisiones
- Reutiliza `ADR-010-tui-opcional-textual-y-telemetria-local.md` manteniendo `textual` como única dependencia opcional de `[tui]` y cero dependencias adicionales para sonidos, notificaciones y TTS.

## Dependencias nuevas
- Ninguna (usa stdlib + utilidades nativas del sistema operativo con degradación segura).

## Plan de prueba
- **Unitarias (`tests/test_telemetry.py`)**:
  - Caché incremental: comprobar que segunda llamada a `collect_telemetry` sin cambios de `mtime_ns`/`size` reutiliza objetos cacheados (`CA-1`).
  - `started_at`, `updated_at` y `duration_seconds` en tasks de Claude Code y Antigravity (`CA-2`).
  - Extracción de `subagents/*.meta.json`+`.jsonl`, `tool-results/*.txt`, `Workflow`, `Skill`, `EnterPlanMode`/`ExitPlanMode`, `teams/` y `touched_files` (`file-history-delta` y ediciones) en ambos agentes (`CA-3`).
  - Detección de `status == "pending"` y `pending_reason` ante `AskUserQuestion`, `ExitPlanMode`, `ask_question` y `tool_use` sin `tool_result` (`CA-4`).
  - Filtrado de bloques de código/diffs para TTS y comandos generados por `SessionController` (`CA-5`, `CA-6`).
- **Tests de TUI (`tests/test_tui.py`)**:
  - Renderizado perezoso por pestaña activa y sincronización al cambiar de pestaña (`CA-1`).
  - Visualización de datetime en `#agents-tasks-table`, alerta `PENDING` + toggle mute `m`, envío de prompt desde el input de la pestaña 3 y activación/corte de `/voice` (`CA-2`..`CA-6`).
- **Verificación en vivo (`live-verify`)**:
  - Ejecutar `aos tui` sobre el repositorio `dass-aos`, verificar carga de sesiones reales de Claude Code y Antigravity con sus subagentes, workflows, archivos tocados y datetimes, probar la barra de prompt, el toggle de alertas/mute y el flujo de voz.

## Observabilidad
- El feed de eventos en vivo (`#live-feed-log`) registra transiciones a `PENDING`, inicio/fin de prompts enviados desde la TUI, activación de `/voice` y cambios en subagentes/workflows.

## Riesgos técnicos
- **Subprocesos de TTS o notificaciones colgados en entornos headless/CI**: Mitigado con timeouts cortos, ejecución en segundo plano y flag `headless` / mocks en tests.

## Referencias
- **Plan**: `.aos/plans/active/009-tui-v2-lazy-loading-workflows-alertas-pending-control-de-sesiones-y-voz.md`
