---
id: 202610031415
type: skill-spec
status: evergreen
cost: on-demand
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

> Inicializa DASS-AOS en cualquier repositorio para las herramientas de IA que se usan: crea `.aos/`, el archivo de instrucciones de cada herramienta (y nada más) y, para `claude-code` y `antigravity`, sus nativos.

## Comando
```bash
aos init [<herramienta>...] [--project-root <path>] [--project-name <name>]
# herramientas: claude-code, antigravity, gemini-cli, codex, opencode, cursor, windsurf
```
- Sin herramienta: usa las de `.aos/config.json` o las que detecta en el repo; si no hay ninguna, falla sin escribir nada.
- Ejecutarlo otra vez con otra herramienta la añade a `.aos/config.json` (`"tools"`).
- Los hooks de inicio de sesión quedan pendientes: revísalos y aplícalos con `aos adapt-native <herramienta> --yes`.
