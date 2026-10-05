---
id: 202610051215
type: decision
status: vigente
created: 2026-10-05
---

# ADR-002: Arquitectura Híbrida CLI y Estado Local (.aos/)

## Contexto
En versiones anteriores (v0.3.0), el workflow asumía una ruta raíz Unix absoluta `/ai-agent-aos/` tanto para los scripts como para los planes, contratos y memorias. Esto provocaba:
1. Fallos inmediatos en Windows (`FileNotFoundError` y `UnicodeEncodeError`).
2. Imposibilidad de trabajar en múltiples proyectos simultáneamente sin mezclar planes activos y contratos.
3. Dependencia de scripts Bash (`.sh`) no ejecutables nativamente en Windows PowerShell / CMD.

## Decisión
Separar limpiamente el **Motor DASS-AOS** del **Estado Local del Proyecto**:
1. **Motor Central**: CLI en Python 3 puro (`aos` / `python aos.py`) sin dependencias externas obligatorias, compatible al 100% con Windows, Linux y macOS.
2. **Estado del Proyecto (`.aos/`)**: Cada proyecto gestiona sus propios contratos (`.aos/contracts/`), planes (`.aos/plans/`), trampas (`.aos/knowledge/gotchas/`) y configuraciones (`.aos/config.json`).
3. **Sincronización Idempotente**: Las directivas para agentes (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules`) se generan con bloques gestionados, preservando las notas humanas.

## Consecuencias
- **Positivas**: Portabilidad universal, soporte nativo de Windows, aislamiento total entre proyectos, empaquetado directo para PyPI y GitHub.
- **Transición**: Se reemplazan scripts `.sh` en `skills/bin/` por módulos de Python en `dass_aos/`, manteniendo shims para compatibilidad.
