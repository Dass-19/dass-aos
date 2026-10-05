---
id: 202610031414
type: skill-spec
status: evergreen
name: "sync-agent-instructions"
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

# Skill: sync-agent-instructions

> Regenera de forma idempotente los bloques gestionados en `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` y `.cursorrules`, preservando íntegras las notas humanas personalizadas.

## Comando
```bash
aos sync [--project-root <path>]
```
