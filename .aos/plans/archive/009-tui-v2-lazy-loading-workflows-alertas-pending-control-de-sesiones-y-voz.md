---
id: 202611180838
type: plan
status: completed
priority: high
tags: [plan/feature, tui, telemetry, sessions, workflows, voice, pty, herdr]
created: 2026-11-18
prd: 003-tui-v2-lazy-loading-workflows-alertas-pending-control-de-sesiones-y-voz.prd.md
trd: 003-tui-v2-lazy-loading-workflows-alertas-pending-control-de-sesiones-y-voz.trd.md
---

# Plan: Feature — TUI v2: Lazy Loading, Workflows, Alertas Pending, Control de Sesiones y Voz

> Objetivo (Definition of Done): Entregar y verificar en vivo `CA-1`..`CA-8` de `.aos/specs/003-tui-v2-lazy-loading-workflows-alertas-pending-control-de-sesiones-y-voz.prd.md` con `aos verify`, `aos scan --dry-run` y `aos doctor` en verde.

## Contexto y Archivos Afectados
- PRD: `.aos/specs/003-tui-v2-lazy-loading-workflows-alertas-pending-control-de-sesiones-y-voz.prd.md` (criterios `CA-1`..`CA-8`)
- TRD: `.aos/specs/003-tui-v2-lazy-loading-workflows-alertas-pending-control-de-sesiones-y-voz.trd.md`
- Archivos previstos:
  - `dass_aos/telemetry.py`
  - `dass_aos/tui/controller.py` (nuevo)
  - `dass_aos/tui/app.py`
  - `dass_aos/tui/widgets.py`
  - `dass_aos/tui/styles.tcss`
  - `tests/test_telemetry.py`
  - `tests/test_tui.py`
- ADRs vinculados: `ADR-010-tui-opcional-textual-y-telemetria-local.md`
- Gotchas a considerar:
  - `windows-cp1252-encoding.md` (`PYTHONUTF8=1` y `encoding="utf-8"` en todos los subprocesos y lecturas)
  - `tokens-por-proyecto-atribucion.md` (atribución de sesiones y subagentes por proyecto)
  - Lección `2026-11-16` en `LEDGER.md` (`set_focus(None)` antes de cambiar `TabbedContent.active` en Textual 8)
- Contratos a crear/actualizar: Esquemas internos en `dass_aos/telemetry.py` y `dass_aos/tui/controller.py` según sección `## Contratos` del TRD `003`.
- Riesgo (ADR-008): **Medio-Alto** (concurrencia entre workers de telemetría, subprocesos de sesiones/TTS y renderizado perezoso de Textual) → verificación en vivo (`live-verify`) + revisión adversarial con recibo (`adversarial-review`).

> La spec se cita, nunca se parafrasea: los handoffs apuntan a la ruta y a la sección del PRD/TRD.

## Fases de Ejecución Atómica

- [x] Fase 1: Discovery & requisitos (`spec-driven` + `/grill-me`)
  - Inspección de `dass_aos/telemetry.py`, `dass_aos/tui/app.py`, `dass_aos/tui/widgets.py`, `~/.claude/` y `~/.gemini/antigravity/brain/`.
  - Entrevista `/grill-me` completada con el usuario (8 decisiones cerradas en el Discovery Trail).
  - PRD y TRD creados y aprobados en `.aos/specs/003-tui-v2-lazy-loading-workflows-alertas-pending-control-de-sesiones-y-voz.{prd,trd}.md`.
  - Gate: `python -m dass_aos status` y `python -m dass_aos doctor` sin errores ni preguntas abiertas.
- [x] Fase 2: Telemetría v2 — Caché incremental, Datetimes en Tasks, Mapeo de Workflows/Subagentes/Archivos y Detección de `Pending` (`CA-1`, `CA-2`, `CA-3`, `CA-4`)
  - Test-first en `tests/test_telemetry.py`: pruebas RED para caché por `(mtime_ns, size)`, `started_at`/`updated_at` en tasks, parseo de `subagents/*.meta.json`+`.jsonl`, `tool-results/*.txt`, `Workflow`/`Skill`/`EnterPlanMode`/`ExitPlanMode`/`teams`, `touched_files` (`file-history-delta` + ediciones) en Claude Code y Antigravity, y detección de `status == "pending"` con `pending_reason`.
  - Implementar en `dass_aos/telemetry.py` cumpliendo secciones `## Contratos` y `## Modelo de datos` del TRD `003`.
  - Gate: `python -m unittest discover -s tests -p "test_telemetry.py"` y `python -m dass_aos verify` en verde. (Verificado: 12 tests en `test_telemetry.py` + `ruff check` OK).
- [x] Fase 3: Controlador de Sesiones estilo Herdr, Alertas Multicanal y Puente `/voice` + TTS (`CA-4`, `CA-5`, `CA-6`)
  - Test-first en `tests/test_tui.py`: pruebas RED para filtrado de texto conversacional de TTS (omitiendo bloques de código/diffs), disparo de alertas en transición a `pending` con respeto a `mute`, y construcción/gestión de comandos de sesión (`send_prompt`, `create_session`, `stop_session`, `trigger_voice`).
  - Implementar `dass_aos/tui/controller.py` (`SessionController`, `AlertDispatcher`, `TTSManager`).
  - Gate: `python -m unittest discover -s tests` y `python -m dass_aos verify` en verde. (Verificado: `TestTuiControllerAndAlerts` + `ruff check` OK).
- [x] Fase 4: Interfaz TUI v2 — Renderizado Perezoso por Pestaña, Datetimes en Tablas, Consola/Prompt en Pestaña 3 y Controles de Voz/Mute (`CA-1`..`CA-6`)
  - Actualizar `dass_aos/tui/widgets.py`, `dass_aos/tui/styles.tcss` y `dass_aos/tui/app.py`:
    - Renderizado perezoso solo de la pestaña activa + sincronización inmediata al cambiar de pestaña (`CA-1`).
    - Columnas de datetime `YYYY-MM-DD HH:MM:SS` + duración/edad en `#agents-tasks-table` y rango completo en el borde del log (`CA-2`).
    - Resumen enriquecido de sesión con `workflows`, `subagents`, `touched_files` y banner/badge `PENDING` con `pending_reason` (`CA-3`, `CA-4`).
    - Barra interactiva en pestaña `3 · Agentes & Tasks` para promptear al agente o responder `pending`, crear sesión con nombre (`n`), detener (`k`), activar `/voice` y silenciar alertas (`m`), más parada de TTS con `Esc` (`CA-4`, `CA-5`, `CA-6`).
  - Ampliar `tests/test_tui.py` con Textual Pilot probando navegación perezosa, prompteo en pestaña 3, mute `m` y zoom `z`.
  - Gate: `python -m dass_aos verify` en verde. (Verificado: 9 tests en `test_tui.py` + `ruff check` OK).
- [x] Fase 5: Verificación en vivo (`live-verify`) y Revisión con recibo (`adversarial-review`) de `CA-1`..`CA-6`
  - Ejecutar `aos tui` en vivo sobre el repositorio `dass-aos` verificando sesiones reales de Claude Code y Antigravity, lazy loading entre pestañas, datetimes de tasks, workflows/archivos tocados, alertas `pending` y controles de sesión/voz.
  - Congelar candidato y ejecutar revisión adversarial registrando recibo, más `aos verify`, `aos scan --dry-run` y `aos doctor`.
  - Gate: Recibo de revisión registrado y `python -m dass_aos verify` + `python -m dass_aos doctor` con 0 errores. (Verificado: 17 sesiones y 192 tasks reales en `live-verify`, hallazgo de `args` JSON-serializados en Antigravity corregido y registrado en `LEDGER.md`, recibo RDD `4fd9086c1019e59b746e735e35602119a4630ef1` cerrado).
- [x] Fase 6: Emulador PTY/ConPTY + VT100 en Vivo y Widget `AgentTerminalWidget` estilo Herdr (`CA-7`, `ADR-011`)
  - Test-first en `tests/test_tui.py`: pruebas RED para el emulador `VtScreen` (secuencias CSI/SGR TrueColor/cursor/clear/OSC title/OSC 7501), el detector en vivo `detect_terminal_agent_state` (reglas `claude.toml` y `agy.toml` para `working`, `pending`/`blocked`, `idle`), la ejecución real en `PtyProcess` (`ConPTY` en Windows / `pty` en Unix), y el widget interactivo `AgentTerminalWidget` en la pestaña 3 (**Modo Terminal** vs **Modo Navegación** con `Ctrl+G`, adjuntar sesión CLI y alternar vista `Terminal` / `Inspector`).
  - Implementar `dass_aos/tui/pty_terminal.py` e integrarlo en `dass_aos/tui/controller.py`, `dass_aos/tui/app.py` y `dass_aos/tui/styles.tcss`.
  - Ejecutar `live-verify` abriendo un proceso interactivo real en el PTY dentro de `aos tui` y cerrar el recibo RDD actualizado.
  - Gate: `python -m dass_aos verify` + `python -m dass_aos doctor` con 0 errores y recibo RDD actualizado. (Verificado: 12 tests en `test_tui.py` + `live-verify` en `task-367` con ConPTY interactivo en vivo + recibo `d5b0c96b3e4826d9ed3b2f4198a1670bbffa0beb`).

- [x] Fase 7: Grafo de Subagentes e Interacciones en Vivo (`CA-8`) y Corrección Acotada 4R (`H1`..`H6`)
  - Test-first en `tests/test_tui.py`: pruebas RED→GREEN para `H1` (altura del PTY `>= 12` filas con resumen compacto y `#agents-log-box` oculto en modo Terminal/Grafo), `H2` (`ZoomScreen` con `AgentTerminalWidget` interactivo en vivo), `H3` (`AgentTerminalWidget.on_key` consume todas las teclas cuando tiene el foco), `H4`/`H5` (`check_alive()` con `WaitForSingleObject`+`GetExitCodeProcess`, liberación de `_hpc`, una sola llamada a `poll_output()` por ciclo, shell interactiva en `cwd` para `antigravity`, sanitización de `CLAUDECODE` en `_build_sanitized_pty_env`), `H6` (ECMA-48 CSI `[\x30-\x3f]*[\x20-\x2f]*[\x40-\x7e]` y `DECSTBM` scroll regions en `VtScreen`), y `test_subagent_graph_view_renders_topology_and_interactions` (`format_subagent_graph` + modo `"graph"` con tecla `g` y botón `Grafo (g)`).
  - Verificación en vivo (`live-verify`): `TAB3 TERM HEIGHT: 21 WIDTH: 74`, escritura interactiva en `ZoomScreen` (`ECHO_FROM_ZOOM:zumba`) y renderizado en vivo del Grafo de Subagentes con los 6 subagentes de la sesión `95938c9c`.
  - Gate: `python -m dass_aos verify` + `python -m dass_aos scan --dry-run` + `python -m dass_aos doctor` en verde.

## Recibo de Revisión (RDD)
- Candidato: `d5b0c96b3e4826d9ed3b2f4198a1670bbffa0beb` (revisado por 4R + verificador) → `0327bc4f4556d17740db5315fa93a62469e2199a` (final tras corrección acotada + Fase 7) · 13 archivos · 2026-11-18 11:38
- Archivos: `dass_aos/telemetry.py`, `dass_aos/tui/pty_terminal.py`, `dass_aos/tui/controller.py`, `dass_aos/tui/app.py`, `dass_aos/tui/widgets.py`, `dass_aos/tui/styles.tcss`, `tests/test_telemetry.py`, `tests/test_tui.py`, `.aos/decisions/ADR-011-terminal-pty-vt100-embebido-estilo-herdr.md`, `.aos/knowledge/gotchas/windows-conpty-startf-usestdhandles.md`, `.aos/knowledge/lessons/LEDGER.md`, `.aos/specs/003-tui-v2-lazy-loading-workflows-alertas-pending-control-de-sesiones-y-voz.prd.md`, `.aos/specs/003-tui-v2-lazy-loading-workflows-alertas-pending-control-de-sesiones-y-voz.trd.md`
- Tier: alto (4R solicitado explícitamente por el usuario: 4 subagentes `reviewer` `R1 Risk`, `R2 Resilience`, `R3 UX`, `R4 Reliability` + 1 subagente `adversarial-verifier`)
- Lentes: 4R (`R1 Risk`, `R2 Resilience`, `R3 UX & Terminal Input`, `R4 Reliability & VT100`)

### Acuse
- Candidato revisado: `d5b0c96b3e4826d9ed3b2f4198a1670bbffa0beb` → `0327bc4f4556d17740db5315fa93a62469e2199a` · tier alto · lentes 4R
- Confirmados: 6 (tras auditoría de los 4 revisores y refutación del `adversarial-verifier` `35ebc33c-1c6a-4b4a-93f7-65afcb035533`)
  1. `critical` (`H1` · R3/R1) · `dass_aos/tui/app.py:258`, `dass_aos/tui/styles.tcss:225`: en modo Terminal, `#agents-activity-box` (`1fr`) y `#agents-log-box` (`1fr`) dividían la columna derecha 50/50 y `#agents-session-summary` (`height: auto`) ocupaba 8–11 líneas, colapsando `#agent-terminal-pane` a `height == 1` (invisible). Reproducido en RED y corregido ocultando `#agents-log-box` en modo Terminal/Grafo, usando `compact=True` (1–2 líneas) en `format_session_detail_summary` y `min-height: 12` (`height == 21` en `live-verify`).
  2. `critical` (`H2` · R3/R1) · `dass_aos/tui/app.py:118` (`ZoomScreen`): al pulsar `z`, `ZoomScreen` montaba un `Static` de solo lectura con `BINDINGS` `z`/`q`/`escape -> dismiss`, impidiendo escribir en el PTY. Corregido pasando `pty_session` a `ZoomScreen` para montar y enfocar un `AgentTerminalWidget` interactivo en vivo.
  3. `high` (`H3` · R3) · `dass_aos/tui/pty_terminal.py:567` (`AgentTerminalWidget.on_key`): las teclas no mapeadas por `encode_terminal_key` no ejecutaban `event.stop()`, filtrándose a `App.BINDINGS`, y faltaba `on_resize` para redimensionar el PTY. Corregido consumiendo todas las teclas cuando el terminal tiene foco, auto-conectando con `Enter` si aún no hay PTY y añadiendo `on_resize`.
  4. `high` (`H4` · R1/R2) · `dass_aos/tui/controller.py:227,258`, `dass_aos/tui/pty_terminal.py:446`: `build_interactive_cli_command` devolvía `[agy.exe]` sin argumentos (launcher GUI Electron que sale de inmediato), `poll_all_ptys` llamaba dos veces seguidas a `poll_output()` descartando el flag `updated`, y en Windows `self.alive` no consultaba `WaitForSingleObject`/`GetExitCodeProcess`. Corregido con `check_alive()`, una sola llamada a `poll_output()`, shell interactiva en `sess.cwd` para `antigravity` y wrapper `COMSPEC /d /s /c` para `.cmd`/`.bat`.
  5. `high` (`H5` · R1/R2) · `dass_aos/tui/pty_terminal.py:390,520`: `CreateProcessW` no pasaba un bloque de entorno sanitizado sin `CLAUDECODE` (`CREATE_UNICODE_ENVIRONMENT = 0x00000400`) y `_hpc` se cerraba después de los pipes con posible doble cierre de FD en Unix. Corregido con `_build_sanitized_pty_env()`, cierre de `ClosePseudoConsole` antes de pipes/proceso y deduplicación de FDs.
  6. `medium` (`H6` · R4/R2) · `dass_aos/tui/pty_terminal.py:26,184`: `_ESC_TOKEN_RE` no incluía bytes intermedios ECMA-48 (`0x20..0x2f` como `CSI 2 SP q` / `CSI ! p`), dejando basura visual (`2 q`, `!p`), `feed()` podía partir `ESC \` (`ST`) entre lecturas y faltaba `DECSTBM` (`CSI r`, `CSI L`, `CSI M`, `ESC M`). Reproducido en RED y corregido en `VtScreen`.
- Refutados: 1 (`dass_aos/tui/controller.py`: supuesta inyección de comandos en PowerShell TTS/Toast → refutado porque el texto se pasa exclusivamente por variables de entorno `$env:AOS_TTS_TEXT` / `$env:AOS_ALERT_MSG`; se añadió `"--"` defensivo en `say`/`spd-say`/`notify-send`).
- Corrección: un solo pase acotado en `pty_terminal.py`, `controller.py`, `app.py`, `widgets.py`, `styles.tcss` y `telemetry.py` + tests RED→GREEN en `tests/test_tui.py` · gates repetidos: `python -m dass_aos verify` + `python -m dass_aos scan --dry-run` + `python -m dass_aos doctor` → verde.
- Pendientes: 0
- Documentos corregidos: `.aos/knowledge/lessons/LEDGER.md`, `.aos/knowledge/gotchas/windows-conpty-startf-usestdhandles.md`, `.aos/decisions/ADR-011-terminal-pty-vt100-embebido-estilo-herdr.md` y `.aos/specs/003-tui-v2-lazy-loading-workflows-alertas-pending-control-de-sesiones-y-voz.{prd,trd}.md`.

## Registro de Preguntas y Decisiones (Discovery Trail)
- **Pregunta 1/6:** Estrategia de optimización y Lazy Loading para proyectos grandes con muchas sesiones en `aos tui`.
  - **Opciones:** 1) Caché incremental por `mtime/size` + renderizado solo de la pestaña activa + lectura bajo demanda del detalle seleccionado; 2) Polling por niveles manteniendo todas las pestañas pre-renderizadas; 3) Carga manual bajo demanda.
  - **Decisión:** Opción 1 (Caché incremental por `mtime/size` + renderizado solo de la pestaña activa + lectura bajo demanda del detalle seleccionado).
  - **Fecha:** 2026-11-18
- **Pregunta 2/6:** Visualización del datetime de ejecución en las tasks en background de ambos agentes.
  - **Opciones:** 1) Guardar `started_at` y `updated_at` en `AgentTaskInfo`, mostrar `YYYY-MM-DD HH:MM:SS` + duración/edad en la tabla y el rango completo (`inicio → fin + duración`) en el encabezado del log; 2) Solo fecha de inicio reemplazando edad; 3) Hora corta en tabla e ISO solo en zoom.
  - **Decisión:** Opción 1 (`started_at` y `updated_at`, datetime `YYYY-MM-DD HH:MM:SS` + duración/edad en tabla y rango completo en el encabezado del log).
  - **Fecha:** 2026-11-18
- **Pregunta 3/6:** Alcance del mapeo de workflows, subagentes, tasks y archivos en sesiones de Claude Code y Antigravity.
  - **Opciones:** 1) Mapear todo en el modelo unificado (subagentes `.meta.json`+`.jsonl`, tasks background `run_in_background`+`tool-results/`, llamadas `Workflow`/`Skill`/`PlanMode`/`Teams`, y archivos tocados `file-history-delta`+`Write`/`Edit`); 2) Pestaña separada exclusiva de workflows; 3) Solo subagentes y workflows sin archivos tocados.
  - **Decisión:** Opción 1 aplicada simétricamente tanto para Claude Code como para Antigravity (subagentes, tasks background, llamadas a workflows/skills y archivos tocados).
  - **Fecha:** 2026-11-18
- **Pregunta 4/6:** Canales de alerta cuando un agente entra en estado `pending` (aprobación de permiso, pregunta al usuario, revisión de plan/artefacto).
  - **Opciones:** 1) Triple alerta con toggle (`m` mute): estado `PENDING` + banner en TUI con el detalle, sonido (`winsound` / `\a`) y notificación nativa de escritorio del SO; 2) Solo banner + sonido en terminal; 3) Solo visual en TUI.
  - **Decisión:** Opción 1 (Triple alerta visual + sonido + notificación nativa del SO, con atajo `m` para silenciar).
  - **Fecha:** 2026-11-18
- **Pregunta 5/6 + Seguimiento 1/2:** Gestión de sesiones e interacción estilo Herdr dentro de `aos tui`.
  - **Opciones:** 1) Integrado en la pestaña `3 · Agentes & Tasks` (con zoom `z` a pantalla completa): lista de sesiones/subagentes/tasks a la izquierda, y a la derecha el visor en vivo / terminal embebida + barra de prompt, botón `/voice` y acciones de sesión (`n` nueva, `k` detener); 2) Pestaña 8 separada; 3) Drawer inferior.
  - **Decisión:** Opción 1 (Integrado en la pestaña `3 · Agentes & Tasks` con visor detallado en vivo, prompteo directo desde la TUI y zoom `z`).
  - **Fecha:** 2026-11-18
- **Pregunta 6/6 + Seguimiento 2/2:** Integración de TTS y STT (`/voice`) en la TUI.
  - **Opciones:** 1) Delegar STT al `/voice` nativo del agente y que la TUI sintetice en voz (TTS nativo del SO sin costo de API) el texto conversacional y las preguntas del agente (omitiendo bloques largos de código/diffs) con corte inmediato (`Esc` o nuevo turno); 2) Leer todo incluyendo código; 3) Solo leer preguntas.
  - **Decisión:** Opción 1 (Delegar al `/voice` nativo para hablarle al agente y responder por voz de forma fluida leyendo el texto conversacional/preguntas vía TTS del SO).
  - **Fecha:** 2026-11-18

## Registro de Bloqueos
- Ninguno
