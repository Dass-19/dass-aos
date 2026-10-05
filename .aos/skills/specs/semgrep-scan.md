---
id: 202610031410
type: skill-spec
status: evergreen
name: "semgrep-scan"
runtime: python
entrypoint: "aos scan --tool semgrep"
inputs:
  - name: project_root
    type: string
    required: false
  - name: dry_run
    type: boolean
    description: "If true (or tool missing in local environment), print guidance and exit 0"
    required: false
outputs:
  format: "stdout | exit-code"
created: 2026-10-03
updated: 2026-10-05
---

<!-- DASS-AOS-GENERATED: no editar; agregados del proyecto en semgrep-scan.local.md -->

# Skill: semgrep-scan

> SAST con Semgrep. Soporta modo dry-run para no romper flujos locales cuando la herramienta no está instalada.

## Comando
```bash
aos scan --tool semgrep [--dry-run]
# O con CLI instalado:
aos scan --tool semgrep [--dry-run]
```

## Exit codes
- 0 → Limpio, modo dry-run, o solo advertencias
- 1 → Hallazgos HIGH/CRITICAL (modo real)
- 2 → Error en ejecución de herramienta
