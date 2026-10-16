---
id: {{YYYYMMDDHHmm}}
type: plan
status: active
priority: medium
tags: [plan/feature]
created: {{YYYY-MM-DD}}
---

# Plan: Feature — {{SHORT_TITLE}}

> Objetivo (Definition of Done): {{MEASURABLE_CRITERIA}}

## Contexto y Archivos Afectados
- Archivos previstos: []
- ADRs vinculados: []
- Gotchas a considerar: []
- Contratos a crear/actualizar: []

## Fases de Ejecución Atómica
> Cada fase termina con su línea `Gate:` (comando exacto y resultado esperado). Una fase no empieza hasta que la anterior la pasa. Flujo completo en la skill `phased-delivery`.

- [ ] Fase 1: Discovery & contratos
  - Línea base: `aos verify` + gates del proyecto; anotar lo que ya falla
  - Clarificar requisitos; decisiones del usuario al Discovery Trail
  - Escribir/actualizar contratos HTTP y/o events
  - Gate: contratos validados
- [ ] Fase 2: Diseño
  - ADR si el alcance es transversal; `NNN-<slug>.design.md` si trabajan varios agentes
  - Generar cliente (`generate-client`) si aplica
  - Gate: plan aprobado
- [ ] Fase 3: Implementación (una subfase por capa, en orden de dependencias)
  - …
  - Gate: `aos verify` + gates del proyecto; lógica nueva con una comprobación vista fallar
- [ ] Fase 4: Verificación en vivo (skill `live-verify`)
  - Levantar la app, ejercitar lo tocado, mirar la evidencia y corregir (≤3 rondas)
  - Gate: evidencia (capturas/logs/salidas) citada aquí; lo no ejercido, a pruebas manuales
- [ ] Fase 5: Revisión adversarial (skill `adversarial-review`)
  - Lentes afectadas → verificador por hallazgo → corregir solo lo confirmado
  - Gate: confirmados, refutados y pendientes anotados; gates repetidos en verde
- [ ] Fase 6: Cierre
  - `aos verify` + `aos scan --dry-run`; marcar plan, gotchas, ADRs, sync agent instructions

## Registro de Preguntas y Decisiones (Discovery Trail)
- **Pregunta:**
- **Opciones:**
- **Decisión:**
- **Fecha:**

## Registro de Bloqueos
-
