---
id: 202610031416
type: skill-spec
status: evergreen
cost: on-demand
name: "git-atomic-commit"
description: "Crea commits atómicos con Conventional Commits y lista explícita de archivos; nunca git add -A."
runtime: python
entrypoint: ".aos/skills/bin/git_atomic_commit.py"
inputs:
  - name: message
    type: string
    required: true
  - name: files
    type: list
    description: "Explicit list of files to stage and commit"
    required: true
outputs:
  format: "exit-code"
created: 2026-10-03
updated: 2026-10-05
---

<!-- DASS-AOS-GENERATED: no editar; agregados del proyecto en git-atomic-commit.local.md -->

# Skill: git-atomic-commit

> Crea commits atómicos verificados con Conventional Commits exigiendo la lista explícita de archivos afectados. Nunca usa `git add -A`.

## Comando
```bash
python .aos/skills/bin/git_atomic_commit.py -m "feat(auth): add token verification" -f src/auth.py src/tokens.py
```
