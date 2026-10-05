# AGENTS.md — Instrucciones del Proyecto

<!-- DASS-AOS-MANAGED-START -->
# Instrucciones Gestionadas por DASS-AOS (v0.4.0 · generado 2026-10-05)

> **Raíz del Estado del Proyecto**: `.aos/`
> Todas las reglas, planes activos, contratos, decisiones y trampas (gotchas) se almacenan localmente en `.aos/`.

## Ciclo de Vida Obligatorio del Agente
1. **Inicio de Sesión (Session-Start)**: Ejecutar `python aos.py refresh` (o `aos refresh`) para revisar gotchas recientes y el estado de memoria.
2. **Pre-Tarea (Pre-Task)**: Consultar `.aos/plans/active/` para tomar la siguiente tarea atómica sin marcar. Revisar `.aos/contracts/` y consultar `codebase-memory` antes de modificar código.
3. **En Tarea (In-Task)**: Trabajar en fases atómicas. Nunca inventar endpoints ni esquemas de eventos que no estén formalmente declarados en `.aos/contracts/`.
4. **Post-Tarea (Post-Task)**: Ejecutar `python aos.py verify` (linters/tests) y `python aos.py scan` (Semgrep/Checkov). Marcar la tarea completada en el plan con `[x]`.

## Roles Especializados Disponibles
`app-builder`, `architect`, `qa-tester`, `refactorer`, `reviewer`, `security-auditor`

## Skills y Comandos Principales Disponibles
`api-smoke-test`, `bootstrap-project`, `checkov-scan`, `db-migration-check`, `generate-client`, `git-atomic-commit`, `init`, `memory-refresh`, `plan`, `refresh`, `scan`, `semgrep-scan`, `sync`, `sync-agent-instructions`, `verify`

## Contratos y Codebase Memory
- **Contratos**: Consulta `.aos/contracts/http/`, `.aos/contracts/events/` y `.aos/contracts/schemas/`.
- **Codebase Memory**: Consulta el grafo estructural (`search_graph`/`query_graph`) antes de alterar arquitecturas cruzadas.
- **Trampas (Gotchas)**: Documenta nuevos aprendizajes y trampas en `.aos/knowledge/gotchas/<nombre>.md`.
- **Decisiones (ADRs)**: Cambios arquitectónicos transversales requieren un ADR bajo `.aos/decisions/`.

## Aviso de Sincronización
No edites este bloque manualmente. Para resincronizar las instrucciones, ejecuta:
```bash
python aos.py sync
```
<!-- DASS-AOS-MANAGED-END -->

## Notas personalizadas del proyecto

(Añade aquí notas libres, detalles específicos del stack y consejos para desarrolladores — se conservarán intactas en cada sincronización)
