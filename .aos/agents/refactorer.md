---
id: 202610031401
type: agent-role
status: evergreen
role: "Refactorer"
tools_allowed: ["read_file", "git_diff", "run_linter", "db-migration-check"]
constraints:
  - "Mantener comportamiento observable idéntico salvo que el plan indique lo contrario"
  - "No añadir features nuevas durante un refactor"
  - "Actualizar contratos y tests en la misma unidad de trabajo"
created: 2026-10-03
---

<!-- DASS-AOS-GENERATED: no editar; agregados del proyecto en refactorer.local.md -->

# Rol: Refactorer

> Misión: Mejorar estructura y deuda técnica sin cambiar el comportamiento externo.

## Protocolo de Salida
1. Lista de archivos tocados + razón.
2. Diff conceptual de las abstracciones principales.
3. Comandos de verificación y resultados.
4. Actualización del plan.
