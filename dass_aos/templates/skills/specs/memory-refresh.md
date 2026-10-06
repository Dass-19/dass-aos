---
id: 202610031413
type: skill-spec
status: evergreen
name: "memory-refresh"
description: "Refresco de inicio de sesión (aos refresh): gotchas recientes, estado de codebase-memory y siguiente tarea del plan activo."
runtime: python
entrypoint: "aos refresh"
inputs:
  - name: project_root
    type: string
    required: false
  - name: gotchas_limit
    type: integer
    description: "How many recent gotchas to surface (default 5)"
    required: false
outputs:
  format: "markdown | stdout"
created: 2026-10-03
updated: 2026-10-05
---

# Skill: memory-refresh

> Ejecutado obligatoriamente al inicio de cada sesión (ver hooks/session-start.md).  
> Consulta el estado de `codebase-memory`, lista los gotchas más recientes y extrae la siguiente tarea del plan activo.

## Comando
```bash
aos refresh [--gotchas-limit 5]
```
