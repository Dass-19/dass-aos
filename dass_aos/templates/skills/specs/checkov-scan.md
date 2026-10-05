---
id: 202610031411
type: skill-spec
status: evergreen
name: "checkov-scan"
runtime: python
entrypoint: "aos scan --tool checkov"
inputs:
  - name: project_root
    type: string
    required: false
  - name: dry_run
    type: boolean
    required: false
outputs:
  format: "stdout | exit-code"
created: 2026-10-03
updated: 2026-10-05
---

# Skill: checkov-scan

> Escaneo de IaC / contenedores / pipelines con Checkov. Soporta `--dry-run`.

## Comando
```bash
aos scan --tool checkov [--dry-run]
# O con CLI instalado:
aos scan --tool checkov [--dry-run]
```
