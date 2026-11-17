---
id: 202611161043
type: prd
status: approved
tags: [spec/prd, tui, observability, agents]
created: 2026-11-16
---

# PRD: TUI de monitoreo en tiempo real

> Para desarrolladores que trabajan con DASS-AOS y agentes de IA (Claude Code, Antigravity u otros): ofrece una interfaz de terminal interactiva (`aos tui`) para observar en tiempo real el avance del plan, los agentes y subagentes activos, las tareas en segundo plano, los cambios en Git, la salud del harness y el conocimiento del proyecto, además de ejecutar comprobaciones sin salir del monitor.

## Problema
Hoy DASS-AOS expone comandos de terminal de una sola ejecución (`aos status`, `aos refresh`, `aos doctor`, `aos context`, `aos verify`, `aos scan`). Cada comando imprime una instantánea estática y termina.
- **Evidencia en el código actual**: `dass_aos/cli.py` ejecuta comandos puntuales y devuelve el control al shell; no existe ningún subcomando de observación continua ni agregador de telemetría de sesiones/tareas de agentes (`~/.claude/`, `~/.gemini/antigravity/brain/`).
- **Impacto**: mientras un agente o varios subagentes trabajan sobre el repositorio en sesiones largas o en segundo plano, el desarrollador tiene que ir ejecutando comandos repetidos a mano y revisando múltiples carpetas para saber en qué fase va el plan, qué archivos tocó el agente, qué tareas en background siguen corriendo o si aparecieron errores en `doctor` o en los tests.

## Usuario y contexto
- **Quién lo usa**: Desarrolladores humanos supervisando agentes de codificación (Human-in-the-Loop) con DASS-AOS en Windows, Linux y macOS.
- **Cuándo y dónde**: En una terminal abierta en la raíz del proyecto (por ejemplo en un panel lateral del IDE o terminal dedicada) mientras el agente ejecuta un plan o trabaja en segundo plano.
- **Qué hace hoy en su lugar**: Ejecuta manualmente `aos status`, `git status`, `aos verify` o inspecciona archivos `.aos/plans/active/*.md` y logs dispersos de Claude Code / Antigravity.

## Alcance
- **Dentro (v1)**:
  - Subcomando `aos tui [--project-root PATH] [--interval SEGUNDOS]` con extra opcional `dass-aos[tui]` (`textual`), manteniendo el núcleo de `dass-aos` sin dependencias obligatorias.
  - **Dashboard en tiempo real**: estado derivado (`Working` / `Checking` / `Ready` / `Needs decision`), progreso del plan activo, siguiente fase, alertas de preguntas sin decisión, resumen de agentes activos, cambios Git y feed de eventos en vivo al detectar cambios.
  - **Explorador de Planes, Specs y ADRs**: checklist en vivo de todas las fases de `.aos/plans/active/` (y consulta de `archive/`), visualización del contenido Markdown del plan, *Discovery Trail*, *specs* (`.aos/specs/`) y decisiones (`.aos/decisions/`).
  - **Monitor de Agentes y Tareas en Background (Claude Code y Antigravity)**:
    - Detección read-only de sesiones activas/recientes de **Claude Code** vinculadas al proyecto (`~/.claude/sessions/*.json`, logs JSONL en `~/.claude/projects/<slug>/`, `~/.claude/tasks/`) y de **Antigravity** (`.aos/native/antigravity-seen.txt`, `~/.gemini/antigravity/brain/<id>/` con `transcript.jsonl`, subagentes y logs `.system_generated/tasks/*.log`).
    - Visor en vivo (*tail*) de la actividad reciente (pasos, `tool_calls`, subagentes) y del log de la tarea seleccionada.
  - **Monitor de Workspace / Git en vivo**: archivos modificados, staged y sin seguimiento (`git status --porcelain`), estadísticas (`git diff --stat`), previsualización de `git diff` por archivo y commits recientes.
  - **Salud, Conocimiento y RAG**: vista de hallazgos de `aos doctor` (`error`/`warn`/`info`), gotchas abiertos ordenados por gravedad, lecciones recientes (`LEDGER.md`), estado de `adapt-native` y buscador interactivo conectado a `aos context` (modo `hybrid` o `lexical`).
  - **Ejecución rápida de acciones (`Runner`)**: disparar en segundo plano dentro de la TUI `aos verify`, `aos scan --dry-run` (o `scan`), `aos sync` y `aos refresh`, viendo el progreso y la salida en vivo sin congelar la interfaz.
- **Fuera de alcance (no-objetivos v1)**:
  - Enviar prompts, interrumpir o escribir en los archivos internos de sesiones de Claude Code o Antigravity (solo lectura).
  - Interfaz web, servidor HTTP o daemon persistente fuera del ciclo de vida de `aos tui`.
  - Edición directa de archivos del repositorio desde la TUI (más allá de ejecutar comandos explícitos del motor como `aos sync`).
  - Requerir `textual` para ejecutar los demás comandos de `aos` (`init`, `status`, `verify`, `context`, etc.).

## Criterios de aceptación (medibles)
- [ ] **CA-1 (Dependencia opcional y arranque seguro)**: `pyproject.toml` declara el extra opcional `tui = ["textual>=0.70"]`. Sin `textual` instalado, todos los demás comandos `aos` funcionan sin error y `aos tui` sale con código distinto de 0 mostrando un mensaje claro con `pip install "dass-aos[tui]"`.
- [ ] **CA-2 (Motor de telemetría stdlib)**: Un módulo puro de stdlib (`dass_aos/telemetry.py`, compatible Python >=3.8) recopila un snapshot estructurado con: estado de `aos status`, planes y fases, specs/ADRs, gotchas/lecciones, hallazgos de `doctor`, estado/diff de Git, sesiones/tareas de Claude Code y Antigravity, y cálculo de eventos delta entre snapshots.
- [ ] **CA-3 (Observabilidad read-only de Claude Code y Antigravity)**: Dada la estructura real o simulada en un directorio temporal de `~/.claude/` y `~/.gemini/antigravity/brain/`, el colector filtra las sesiones pertenecientes al `project_root`, extrae pasos/tool calls recientes, subagentes y logs de tareas en background, y no lanza excepciones ante JSON/JSONL incompletos o en escritura concurrente.
- [ ] **CA-4 (Interfaz TUI navegable con vistas completas)**: `aos tui` renderiza en Textual vistas diferenciadas y navegables por teclado (`1`..`6` o pestañas) y ratón para: Resumen/Dashboard, Planes & Specs, Agentes & Tasks, Git & Diff, Conocimiento & Doctor (con buscador `aos context`), y Consola/Acciones (`verify`, `scan`, `sync`, `refresh`).
- [ ] **CA-5 (Refresco en tiempo real no bloqueante)**: La TUI actualiza el snapshot periódicamente (`--interval`, por defecto `1.5s`) y bajo demanda (`r`) en un worker fuera del hilo de renderizado, registrando cambios detectados en un feed de eventos en vivo sin perder foco ni romper la interacción.
- [ ] **CA-6 (Acciones en background dentro de la TUI)**: Al pulsar los atajos/botones de acción (`v` verify, `s` scan --dry-run, `y` sync, `f` refresh), el comando corre en segundo plano sin congelar el refresco ni la navegación, mostrando estado (`running` / `passed` / `failed`), duración y salida en vivo.
- [ ] **CA-7 (Tests y verificación en vivo)**: Suite de tests unitarios para `telemetry.py` (ejecutable en CI Python 3.8–3.12 sin `textual`) + tests de TUI con Textual Pilot (cuando `textual` esté disponible) + verificación en vivo (`live-verify`) ejecutando `aos tui` sobre el repositorio `dass-aos`, manteniendo `aos verify` y `aos doctor` en verde.

## Riesgos de producto
- **Ruido o saturación visual**: mostrar demasiados logs o diffs enormes puede dificultar ver en qué va el agente. Mitigación: jerarquía por pestañas, límites/truncado seguro en lecturas de logs/diffs y feed de eventos resumido en el dashboard.
- **Fragilidad ante cambios internos de Claude Code o Antigravity**: los formatos en `~/.claude/` y `~/.gemini/antigravity/` no son APIs públicas garantizadas. Mitigación: parsers defensivos con degradación limpia por campo y sin acoplar el núcleo de `.aos/` a esos formatos.

## Preguntas abiertas
- Ninguna (alcance completo, extra opcional `[tui]` con Textual y flujo spec-driven aprobados en el Discovery Trail).

## Referencias
- **TRD**: `002-tui-de-monitoreo-en-tiempo-real.trd.md`
- **ADR**: `.aos/decisions/ADR-010-tui-opcional-textual-y-telemetria-local.md`
- **Plan**: `.aos/plans/active/008-tui-de-monitoreo-en-tiempo-real.md`
