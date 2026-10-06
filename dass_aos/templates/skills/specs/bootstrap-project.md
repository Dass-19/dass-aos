---
id: 202610031415
type: skill-spec
status: evergreen
name: "bootstrap-project"
description: "Inicializa DASS-AOS en un repositorio (aos init): estructura .aos/ e instrucciones de agentes sincronizadas."
runtime: python
entrypoint: "aos init"
inputs:
  - name: project_root
    type: string
    required: false
  - name: project_name
    type: string
    required: false
outputs:
  format: "stdout"
created: 2026-10-03
updated: 2026-10-05
---

# Skill: bootstrap-project

> Inicializa DASS-AOS en cualquier repositorio, creando la estructura `.aos/` y los archivos de instrucciones de agentes sincronizados (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules`).

## Comando
```bash
aos init [--project-root <path>] [--project-name <name>]
```
