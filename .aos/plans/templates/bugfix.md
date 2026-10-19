---
id: {{YYYYMMDDHHmm}}
type: plan
status: active
priority: high
tags: [plan/bugfix]
created: {{YYYY-MM-DD}}
---

# Plan: Bugfix — {{SHORT_TITLE}}

> Objetivo (Definition of Done): El comportamiento incorrecto desaparece y existe un test de regresión que lo demuestra.

## Contexto
- Síntoma:
- Reproducción:
- Archivos sospechosos: []
- Gotchas relacionados: []
- PRD/TRD (solo si el fix cambia el contrato con el usuario): []

## Fases
- [ ] Fase 1: Reproducir y aislar (en vivo con `live-verify` si es UI, API o CLI)
  - Gate: pasos de reproducción y evidencia del fallo anotados aquí
- [ ] Fase 2: Escribir test de regresión que falle
  - Gate: el test falla con el código actual
- [ ] Fase 3: Implementar el fix mínimo en la causa raíz (revisar todos los llamadores)
  - Gate: el test pasa + `aos verify`
- [ ] Fase 4: Verificar (`live-verify` sobre la reproducción, una lente de `adversarial-review`, security skills en dry-run si hace falta)
  - Gate: la reproducción ya no falla
- [ ] Fase 5: Cierre (plan, gotcha si aplica, sync)

## Discovery Trail / Bloqueos
-
