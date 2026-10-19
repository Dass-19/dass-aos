# Registro de Lecciones (LEDGER)

Una línea por lección **con evidencia**. No es un diario y no lleva opiniones: es lo que el
motor aprendió y puede volver a usar. Alimenta `aos refresh` al inicio de sesión.

| Fecha | Artefacto tocado | Evidencia (comando o salida) | Efecto |
|---|---|---|---|
| 2026-10-19 | `dass_aos/doctor.py` | `aos doctor` marcaba `checkov-scan.md` y `db-migration-check.md` como «no aparece en las instrucciones» siendo skills condicionales | Un check que no distingue diseño de defecto genera ruido y se acaba ignorando: ahora lo condicional es `info` y solo `applies_when` malformado es `error` |
| 2026-10-19 | `dass_aos/templates/specs/` | `aos init` copiaba `prd.md`/`trd.md` dentro de `.aos/specs/`, donde se confunden con specs reales | Las plantillas van a `.aos/specs/templates/`, igual que `.aos/plans/templates/` |
| 2026-10-19 | `dass_aos/backup.py` | Poda con `MAX_SNAPSHOTS + 3` directorios dejaba 21: se podaba antes de crear el snapshot actual | La poda va después de copiar y conserva los 20 más recientes |
