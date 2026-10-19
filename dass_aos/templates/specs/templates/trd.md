---
id: {{YYYYMMDDHHmm}}
type: trd
status: draft
tags: [spec/trd]
created: {{YYYY-MM-DD}}
prd:
---

# TRD: {{SHORT_TITLE}}

> Cómo se construye y por qué así. **No repite el PRD: lo cita.** El requisito vive en el PRD; aquí solo viven las decisiones técnicas.

## Contexto
- **PRD**: `NNN-<slug>.prd.md` — criterios de aceptación que cubre esta solución: CA-1, CA-2
- Archivos y componentes previstos: []

## Arquitectura y límites
- **Componentes tocados**:
- **Fronteras** (qué NO cruza esta solución, aunque parezca cómodo):

## Contratos
> Contract-first (ADR-001). Si algo de aquí no está declarado, se declara antes de implementarlo.
- **HTTP**: `.aos/contracts/http/<especificacion>.yaml` (crear / actualizar / sin cambios)
- **Eventos**: `.aos/contracts/events/<Esquema>.vN.json`
- **Esquemas / tipos**:

## Modelo de datos
- Tablas, campos y claves:
- Migración (y su idempotencia):

## Decisiones
- ADRs vinculados: []

## Dependencias nuevas
- (Ninguna sin ADR.)

## Plan de prueba
- **Unitarias**:
- **De contrato**:
- **Verificación en vivo** (`live-verify`): qué se levanta, qué se ejercita y qué evidencia se espera

## Observabilidad
- Cómo se detecta en producción que esto falla (log, métrica, error de frontera).

## Riesgos técnicos
- (Qué parte es la más probable que se rompa y por qué.)

## Referencias
- **Plan**: pendiente (`aos plan new feature --title "{{SHORT_TITLE}}"`)
