# GEMINI.md — Instrucciones del Proyecto

<!-- DASS-AOS-MANAGED-START -->
# Instrucciones Gestionadas por DASS-AOS (v0.5.0 · generado 2026-10-06)

> **Raíz del Estado del Proyecto**: `.aos/`
> Todas las reglas, planes activos, contratos, decisiones y trampas (gotchas) se almacenan localmente en `.aos/`.

## Ciclo de Vida Obligatorio del Agente
1. **Inicio de Sesión (Session-Start)**: Ejecutar `aos refresh` (o `python -m dass_aos refresh`) para revisar gotchas recientes y el estado de memoria. Si tu herramienta tiene el hook nativo generado por `adapt-native`, ya se ejecuta solo.
2. **Pre-Tarea (Pre-Task)**: Consultar `.aos/plans/active/` para tomar la siguiente tarea atómica sin marcar. Revisar `.aos/contracts/` y consultar `codebase-memory` antes de modificar código.
3. **En Tarea (In-Task)**: Trabajar en fases atómicas. Nunca inventar endpoints ni esquemas de eventos que no estén formalmente declarados en `.aos/contracts/`.
4. **Post-Tarea (Post-Task)**: Ejecutar `aos verify` (linters/tests) y `aos scan` (Semgrep/Checkov). Marcar la tarea completada en el plan con `[x]`.

## Adaptación Nativa (ADR-004)
Si no existe `.aos/native/<tu-herramienta>.json` o `aos refresh` lo marca DESACTUALIZADO, ejecuta la skill `adapt-native` (`.aos/skills/specs/adapt-native.md`): genera tus subagentes, skills, hooks y MCP nativos desde `.aos/`.

## Roles Especializados Disponibles
`app-builder`, `architect`, `qa-tester`, `refactorer`, `reviewer`, `security-auditor`

## Skills y Comandos Principales Disponibles
`adapt-native`, `api-smoke-test`, `bootstrap-project`, `generate-client`, `git-atomic-commit`, `init`, `memory-refresh`, `plan`, `refresh`, `scan`, `semgrep-scan`, `sync`, `sync-agent-instructions`, `verify`

## Contratos y Codebase Memory
- **Contratos**: Consulta `.aos/contracts/http/`, `.aos/contracts/events/` y `.aos/contracts/schemas/`.
- **Codebase Memory**: Consulta el grafo estructural (`search_graph`/`query_graph`) antes de alterar arquitecturas cruzadas.
- **Trampas (Gotchas)**: Documenta nuevos aprendizajes y trampas en `.aos/knowledge/gotchas/<nombre>.md`.
- **Decisiones (ADRs)**: Cambios arquitectónicos transversales requieren un ADR bajo `.aos/decisions/`.
- **Roles de Agentes**: Consulta directivas y límites en `.aos/agents/<rol>.md`.
- **Ciclo de Vida (Hooks)**: Consulta especificaciones en `.aos/hooks/` (`session-start.md`, `pre-task.md`, `post-task.md`).
- **Skills y Herramientas**: Consulta especificaciones en `.aos/skills/specs/` y utilidades en `.aos/skills/bin/`.

## Directivas para Gemini / Antigravity
- Aprovecha activamente las herramientas MCP de codebase-memory.
- Sigue estrictamente las fases del plan activo sin saltar pasos de verificación.

## Aviso de Sincronización
No edites este bloque manualmente. Para resincronizar las instrucciones, ejecuta:
```bash
aos sync
```
<!-- DASS-AOS-MANAGED-END -->

## Notas personalizadas del proyecto

(Añade aquí notas libres, detalles específicos del stack y consejos para desarrolladores — se conservarán intactas en cada sincronización)
