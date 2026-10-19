---
id: {{YYYYMMDDHHmm}}
type: plan
status: active
priority: medium
tags: [plan/refactor]
created: {{YYYY-MM-DD}}
---

# Plan: Refactor — {{SHORT_TITLE}}

> Objetivo (Definition of Done): Misma superficie observable, mejor estructura interna, tests verdes, contratos intactos (o versionados).

## Contexto
- Motivación (deuda, legibilidad, rendimiento…):
- Archivos previstos: []
- ADRs vinculados: []
- PRD/TRD: normalmente **no aplica** (el comportamiento observable no cambia); si cambia el contrato con el usuario, aplícalos.

## Fases
- [ ] Fase 1: Baseline (tests + metrics actuales)
  - Gate: resultados de referencia anotados aquí
- [ ] Fase 2: Cambios estructurales atómicos
  - Gate: `aos verify` en verde tras cada cambio
- [ ] Fase 3: Actualizar tests / contratos si la firma pública cambia
  - Gate: contratos intactos o versionados
- [ ] Fase 4: Verificación completa (`live-verify` si hay superficie observable; lente de correctitud de `adversarial-review`)
  - Gate: misma salida observable que en la Fase 1
- [ ] Fase 5: Cierre

## Discovery Trail / Bloqueos
-
