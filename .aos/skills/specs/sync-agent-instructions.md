---
id: 202610031414
type: skill-spec
status: evergreen
cost: on-demand
name: "sync-agent-instructions"
description: "Regenera de forma idempotente los bloques gestionados de CLAUDE.md, AGENTS.md, GEMINI.md, etc., preservando las notas humanas."
runtime: python
entrypoint: "aos sync"
inputs:
  - name: project_root
    type: string
    required: false
outputs:
  format: "stdout"
created: 2026-10-03
updated: 2026-10-05
---

<!-- DASS-AOS-GENERATED: no editar; agregados del proyecto en sync-agent-instructions.local.md -->

# Skill: sync-agent-instructions

> Regenera de forma idempotente los bloques gestionados en `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` y `.cursorrules`, preservando íntegras las notas humanas personalizadas.

## Comando
```bash
aos sync [--project-root <path>]
```
