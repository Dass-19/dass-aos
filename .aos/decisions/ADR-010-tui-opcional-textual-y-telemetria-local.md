---
id: 202611161044
type: decision
status: vigente
created: 2026-11-16
---

# ADR-010: TUI interactiva con Textual opcional (`[tui]`) y telemetría local read-only

## Contexto
DASS-AOS cuenta con comandos CLI puntuales (`status`, `refresh`, `doctor`, `context`, `verify`, `scan`), pero carece de una vista en tiempo real para supervisar el progreso de planes, agentes activos (Claude Code y Antigravity), tareas en segundo plano y cambios en el repositorio.

Al mismo tiempo, el núcleo de `dass-aos` (`ADR-002`, `ADR-009`, `pyproject.toml`) no tiene dependencias externas obligatorias y la matriz de CI verifica Python `3.8` a `3.12` con `pip install -e .` sin extras.

## Decisión
1. **Textual como extra opcional `[tui]` en `pyproject.toml`**:
   - Se añade `tui = ["textual>=0.70"]` en `[project.optional-dependencies]`.
   - `dass_aos/tui/` se importa de forma perezosa solo al ejecutar `aos tui`. Si `textual` no está disponible, se informa claramente cómo instalarlo (`pip install "dass-aos[tui]"`) sin afectar al resto de la CLI.
2. **Separación entre telemetría stdlib y presentación**:
   - `dass_aos/telemetry.py` concentra la agregación de estado `.aos/`, Git, sesiones/tareas de Claude Code y Antigravity y detección de eventos delta usando exclusivamente la biblioteca estándar de Python (`>=3.8`), siendo reutilizable y 100% testeable en CI sin `[tui]`.
3. **Observabilidad estrictamente read-only y defensiva sobre herramientas de IA**:
   - La lectura de `~/.claude/` y `~/.gemini/antigravity/brain/` nunca escribe ni bloquea archivos de las herramientas externas, tolera JSON/JSONL truncados o concurrentes y filtra las sesiones por `project_root`: en Antigravity, por el workspace registrado en `conversation_summaries.db`, no por menciones de la ruta en el texto (ver gotcha `tokens-por-proyecto-atribucion.md`).

## Consecuencias
- **Positivas**: Cero impacto en instalaciones mínimas de `dass-aos` y compatibilidad intacta con Python 3.8 en el núcleo; UI interactiva moderna (paneles, scroll, búsqueda, workers asíncronos y soporte de ratón/teclado en Windows, Linux y macOS) cuando se instala `[tui]`.
- **Negativas / Trade-offs**: La TUI completa requiere Python `>=3.9` (requisito de `textual`) e instalación explícita del extra `[tui]`; los parsers de Claude Code y Antigravity dependen de convenciones locales actuales de disco, por lo que están aislados y degradan sin fallar si cambian.

## Condiciones de Revocación
Se revisará si en el futuro `dass-aos` eleva su versión mínima global a Python 3.9+ o si se incorpora un protocolo estándar de eventos emitido directamente por los agentes/hooks.
