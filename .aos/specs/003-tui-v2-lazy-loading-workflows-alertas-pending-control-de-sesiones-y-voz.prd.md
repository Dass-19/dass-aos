---
id: 202611180838
type: prd
status: approved
tags: [spec/prd, tui, sessions, workflows, notifications, voice, performance]
created: 2026-11-18
---

# PRD: TUI v2: Lazy Loading, Workflows, Alertas Pending, Control de Sesiones y Voz

> Evoluciona `aos tui` de un monitor pasivo a un centro de mando interactivo estilo Herdr con carga perezosa para proyectos grandes, trazabilidad completa de workflows/subagentes/archivos de Claude Code y Antigravity, timestamps completos en background tasks, alertas multicanal para agentes en estado `pending`, control directo de sesiones/prompts desde la TUI y respuesta hablada (TTS) sincronizada con `/voice`.

## Problema
En `aos tui` v1 (`002-tui-de-monitoreo-en-tiempo-real.prd.md`) existen seis limitaciones medidas en el código actual (`dass_aos/telemetry.py` y `dass_aos/tui/app.py`):
1. **Recarga redundante en proyectos grandes**: Cada tick de `1.5s` re-lee las colas JSONL de todas las sesiones listadas, todos los `.log` de tasks y el markdown completo de los planes activos, además de actualizar las 7 pestañas de Textual aunque 6 estén ocultas.
2. **Falta de datetime de ejecución en background tasks**: `AgentTaskInfo` solo almacena `updated_at: float` y las tablas muestran edad relativa (`5m`, `2h`), sin fecha/hora de inicio (`started_at`), rango de ejecución ni duración.
3. **Mapeo incompleto del workflow de Claude Code y Antigravity**: `_collect_claude_tasks` solo inspecciona `~/.claude/tasks/<session_id>/` (normalmente vacío), ignorando `<session_id>/subagents/agent-*.meta.json` + `*.jsonl`, `<session_id>/tool-results/*.txt`, invocaciones de `Workflow` (`.claude/workflows/*.js`), `Skill`, `EnterPlanMode`/`ExitPlanMode` (`~/.claude/plans/*.md`), `teams/` y los archivos tocados por sesión (`file-history-delta` / `Write` / `Edit`). En Antigravity tampoco se listan como entidades rastreables las invocaciones `run_workflow`, subagentes con su propio transcript ni los archivos modificados por sesión.
4. **Agentes bloqueados en `pending` sin aviso**: Cuando un agente espera aprobación de herramienta, `AskUserQuestion`/`ask_question`, `ExitPlanMode` o `RequestFeedback`, el usuario no recibe alerta sonora ni notificación del sistema operativo si está en otra ventana.
5. **Múltiples terminales abiertas para dirigir sesiones**: No es posible iniciar sesiones nombradas (slugs estilo Herdr), ver la terminal/salida en vivo a detalle ni enviar prompts o responder preguntas pendientes desde `aos tui`.
6. **Asimetría en interacción por voz (`/voice`)**: Cuando el usuario utiliza `/voice` (STT nativo del agente), el agente responde solo en texto sin devolver retroalimentación hablada (TTS).

## Usuario y contexto
- **Quién lo usa**: Desarrolladores que coordinan una o varias sesiones de Claude Code y Antigravity sobre repositorios medianos o grandes desde `aos tui`.
- **Cuándo y dónde**: En una única terminal con `aos tui` abierta como centro de operaciones para supervisar planes, consumo de tokens, diffs Git y dirigir a los agentes por teclado o voz.
- **Qué hace hoy en su lugar**: Mantiene múltiples terminales o pestañas abiertas (o herramientas externas como Herdr) y alterna manualmente entre ellas para revisar si algún agente se detuvo a pedir permiso o hacer una pregunta.

## Alcance
- **Dentro**:
  - **Lazy Loading y caché incremental**: Caché en memoria indexado por `(path, mtime_ns, size)` para planes, sesiones JSONL, subagentes y logs de tasks; actualización en cada tick únicamente del header y de la pestaña activa en Textual; lectura bajo demanda del detalle seleccionado (markdown de plan/spec/ADR, `git diff`, log de task o actividad de sesión).
  - **Datetime completo en Tasks en Background**: `started_at` y `updated_at` en `AgentTaskInfo` para Claude Code, Antigravity y `tui-runner`, mostrando `YYYY-MM-DD HH:MM:SS` + duración/edad en las tablas y el rango `inicio → fin (duración)` en el encabezado del visor de log.
  - **Mapeo integral de Workflows, Subagentes, Tasks y Archivos tocados (Claude Code y Antigravity)**:
    - Subagentes de Claude (`<session>/subagents/agent-*.meta.json` + `.jsonl`) y de Antigravity (`invoke_subagent` / `define_subagent` / `swarm` + directorio `brain/<sub_id>`).
    - Tasks en background de ambos (`run_in_background`, `<session>/tool-results/*.txt`, `TaskOutput`/`TaskStop`, `CronCreate`, `Monitor`, `.system_generated/tasks/*.log`, `schedule`).
    - Ejecuciones de `Workflow` (`.claude/workflows/*` y `run_workflow`), `Skill`, `EnterPlanMode`/`ExitPlanMode` y `teams/`.
    - Lista de archivos creados/modificados por cada sesión (`file-history-delta` y llamadas `Write`/`Edit`/`write_file`/`edit_file`/`replace_file_content`).
  - **Detección de estado `pending` y triple alerta con mute (`m`)**:
    - Detección automática cuando una sesión espera aprobación de herramienta, respuesta a `AskUserQuestion`/`ask_question`, aprobación de plan (`ExitPlanMode`) o `RequestFeedback`.
    - Triple aviso al entrar en `pending`: 1) badge/banner `PENDING` en la TUI con el detalle de la pregunta o permiso requerido, 2) alerta sonora (`winsound` en Windows / campana `\a` multiplataforma), y 3) notificación nativa del sistema operativo (Toast de escritorio), silenciable con el atajo `m`.
  - **Control de sesiones estilo Herdr en la pestaña `3 · Agentes & Tasks`**:
    - Visor en vivo / terminal embebida en el panel derecho (con zoom `z` a pantalla completa) para ver al detalle lo que hace el agente o subagente seleccionado.
    - Barra de prompt integrada en la pestaña 3 para enviar instrucciones a la sesión seleccionada, responder preguntas en `pending`, crear nuevas sesiones con nombre/slug (`n`) o detener procesos activos (`k`).
  - **Respuesta por voz fluida sincronizada con `/voice`**:
    - Delegación del STT al modo `/voice` nativo del agente y botón/atajo `/voice` en la barra de la sesión.
    - Cuando el turno del usuario proviene de `/voice` (o el modo voz está activo en la sesión), la TUI sintetiza en voz (TTS nativo del SO / SAPI sin costo de API) el texto conversacional y las preguntas del agente (omitiendo bloques largos de código o diffs), permitiendo cortar el audio con `Esc` o al volver a hablar.
- **Fuera (no-objetivos)**:
  - Reemplazar el motor STT nativo de `/voice` con modelos locales pesados (Whisper/PyTorch) ni requerir claves de API de pago para TTS/STT.
  - Servidor web externo o base de datos remota fuera del entorno local del usuario.

## Criterios de aceptación (medibles)
- [x] **CA-1 (Lazy Loading y caché por `mtime/size`)**: En `collect_telemetry`, los archivos de planes, sesiones JSONL, subagentes y `.log` cuyo `(mtime_ns, size)` no haya cambiado no se vuelven a parsear desde disco; y en `AosTuiApp`, cada tick periódico solo re-renderiza el header y la pestaña activa (`TabbedContent.active`), cargando el detalle del documento/diff/log al cambiar de pestaña o de fila seleccionada.
- [x] **CA-2 (Datetime de ejecución en Tasks)**: `AgentTaskInfo` expone `started_at` y `updated_at` (epoch float) para tasks de Claude Code, Antigravity y `tui-runner`; la tabla `#agents-tasks-table` muestra el datetime `YYYY-MM-DD HH:MM:SS` de ejecución junto con su duración/edad, y el borde del panel de log muestra inicio, fin/última actualización y duración.
- [x] **CA-3 (Mapeo completo de Workflows, Subagentes, Tasks y Archivos tocados)**: Dado un proyecto con sesiones de Claude Code y Antigravity que incluyen `subagents/*.meta.json`+`.jsonl`, `tool-results/*.txt`, llamadas `Workflow`, `Skill`, `EnterPlanMode`/`ExitPlanMode`, `run_in_background`, `run_workflow` y `file-history-delta`/ediciones, `collect_telemetry` popula las tasks, subagentes, workflows y `touched_files` en `AgentSessionInfo` y `AgentTaskInfo`, mostrándolos en la pestaña `3 · Agentes & Tasks`.
- [x] **CA-4 (Detección de `pending` y triple alerta con toggle `m`)**: Cuando una sesión queda esperando al usuario (`AskUserQuestion`/`ask_question`, `ExitPlanMode`, `RequestFeedback` o `tool_use` pendiente de aprobación), su `status` pasa a `"pending"` con `pending_reason` descriptivo, y al producirse la transición a `"pending"` la TUI actualiza el banner visual, emite sonido y dispara la notificación del SO (salvo que el modo mute `m` esté activo).
- [x] **CA-5 (Control de sesiones estilo Herdr en pestaña 3)**: Desde `3 · Agentes & Tasks`, el usuario puede crear una sesión nombrada (`n`), seleccionar cualquier sesión/subagente para ver su consola/stream detallado en vivo (y maximizarlo con `z`), enviar un prompt o respuesta desde el input integrado en la pestaña 3 y detener una sesión/proceso gestionado (`k`).
- [x] **CA-6 (Interacción fluida por voz con `/voice` + TTS)**: Al activar `/voice` en la sesión desde la TUI (o detectar un turno enviado con `/voice`), la TUI envía el comando al agente y, al recibir la respuesta o pregunta del asistente, lee en voz alta únicamente el texto conversacional/preguntas (filtrando bloques de código ```...``` y diffs) mediante el TTS nativo del sistema operativo, deteniendo la locución inmediatamente al pulsar `Esc` o iniciar un nuevo turno.
- [x] **CA-7 (Terminal PTY/ConPTY + VT100 en vivo estilo Herdr)**: En la pestaña `3 · Agentes & Tasks`, abrir o adjuntar cualquier sesión levanta un pseudo-terminal real (`ConPTY` en Windows / `pty` en Unix) con emulador de pantalla VT100/ANSI 2D (`VtScreen` en `dass_aos/tui/pty_terminal.py`), mostrando la interfaz CLI del agente trabajando en tiempo real (`claude --resume <id>`, `claude`, `agy`, etc.), reenviando teclas crudas en **Modo Terminal** (saliendo con `Ctrl+G`/`Ctrl+B` al **Modo Navegación**) y clasificando el estado en vivo (`working`, `pending`/`blocked`, `idle`) mediante las reglas de pantalla y secuencias OSC (`0`/`2`/`7501`).
- [x] **CA-8 (Grafo de Subagentes e Interacciones en Vivo)**: En la pestaña `3 · Agentes & Tasks`, el usuario puede activar la vista de grafo (`g` o botón `Grafo (g)`) para visualizar el nodo coordinador de la sesión seleccionada, sus subagentes y workflows delegados (`invoke_subagent`, `Agent`, `Task`, `swarm`, `run_workflow`) con estado en vivo (`running`, `active`, `finished`), rol/tipo, duración y flechas de interacción/mensajes (`──[spawn]──►`, `──[send_message]──►`, `◄──[report]──`).

## Riesgos de producto
- **Ruido auditivo si el TTS lee código o si las alertas suenan en cada tick**: Mitigado disparando alertas solo en la transición de estado (`prev.status != "pending" -> curr.status == "pending"`), filtrando bloques de código/comandos antes del TTS y ofreciendo corte inmediato (`Esc`) y mute global (`m`).
- **Sobrecarga al abrir sesiones con decenas de subagentes**: Mitigado por el caché incremental `(mtime_ns, size)` de `CA-1` y lectura bajo demanda del log/transcript seleccionado.

## Preguntas abiertas
- Ninguna (todas las ramas del árbol de diseño fueron resueltas durante `/grill-me` y registradas en el Discovery Trail del plan `009`).

## Referencias
- **TRD**: `003-tui-v2-lazy-loading-workflows-alertas-pending-control-de-sesiones-y-voz.trd.md`
- **Plan**: `.aos/plans/active/009-tui-v2-lazy-loading-workflows-alertas-pending-control-de-sesiones-y-voz.md`
- **Spec previa**: `002-tui-de-monitoreo-en-tiempo-real.prd.md`
