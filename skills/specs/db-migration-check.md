---
id: 202610031418
type: skill-spec
status: evergreen
name: "db-migration-check"
runtime: python
entrypoint: "aos verify --type migration"
inputs:
  - name: project_root
    type: string
    required: false
outputs:
  format: "exit-code"
created: 2026-10-03
updated: 2026-10-05
---

# Skill: db-migration-check

> Valida que las migraciones de base de datos sean atómicas, reversibles y seguras, ejecutando el comando configurado en `.aos/config.json`.

## Comando
```bash
python aos.py verify --type migration
```
