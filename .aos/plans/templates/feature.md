---
id: {{YYYYMMDDHHmm}}
type: plan
status: active
priority: medium
tags: [plan/feature]
created: {{YYYY-MM-DD}}
prd:
trd:
---

# Plan: Feature — {{SHORT_TITLE}}

> Objetivo (Definition of Done): {{MEASURABLE_CRITERIA}}

## Contexto y Archivos Afectados
- PRD: `.aos/specs/NNN-<slug>.prd.md` (criterios de aceptación que cubre: CA-1, CA-2)
- TRD: `.aos/specs/NNN-<slug>.trd.md`
- Archivos previstos: []
- ADRs vinculados: []
- Gotchas a considerar: []
- Contratos a crear/actualizar: []
- Riesgo (ADR-008): datos / seguridad / contratos compartidos / concurrencia / entrega — y profundidad de revisión que implica

> La spec se cita, nunca se parafrasea: los handoffs apuntan a la ruta y a la sección del PRD/TRD.

## Fases de Ejecución Atómica
> Cada fase termina con su línea `Gate:` (comando exacto y resultado esperado). Una fase no empieza hasta que la anterior la pasa. Flujo completo en la skill `phased-delivery`. El tamaño de la tarea se decide por riesgo y comprensión, no por número de archivos (ADR-008).

- [ ] Fase 1: Discovery & requisitos
  - Línea base: `aos verify` + gates del proyecto; anotar lo que ya falla
  - Clarificar requisitos con el usuario; decisiones al Discovery Trail
  - PRD y TRD (`aos spec new prd|trd`, skill `spec-driven`) si tiene alcance de producto
  - Escribir/actualizar contratos HTTP y/o events
  - Gate: PRD con criterios medibles, TRD que cita el PRD y contratos validados
- [ ] Fase 2: Diseño
  - ADR si el alcance es transversal; `NNN-<slug>.design.md` si trabajan varios agentes
  - Generar cliente (`generate-client`) si aplica
  - Gate: plan aprobado
- [ ] Fase 3: Implementación (una subfase por capa, en orden de dependencias)
  - Test-first: una comprobación RED por regla pedida y una que pruebe que el comportamiento previo sigue
  - Gate: `aos verify` + gates del proyecto; cada lógica nueva con una comprobación vista fallar
- [ ] Fase 4: Verificación en vivo (skill `live-verify`)
  - Levantar la app, ejercitar lo tocado, mirar la evidencia y corregir (≤3 rondas)
  - Gate: evidencia (capturas/logs/salidas) citada aquí; lo no ejercido, a pruebas manuales
- [ ] Fase 5: Revisión con recibo (skill `adversarial-review`, ADR-008)
  - Congelar el candidato (hash/diff) **antes** de que nadie lo lea; profundidad según riesgo: 0 lentes (pasivo), 1 (medio) o 4R (alto)
  - Lentes → verificación adversarial por hallazgo → una única corrección acotada → acuse
  - Gate: recibo anotado; confirmados, refutados y pendientes registrados; gates repetidos en verde
- [ ] Fase 6: Cierre
  - `aos verify` + `aos scan --dry-run`; marcar plan, gotchas, ADRs, sync agent instructions

## Registro de Preguntas y Decisiones (Discovery Trail)
- **Pregunta:**
- **Opciones:**
- **Decisión:**
- **Fecha:**

## Registro de Bloqueos
-
