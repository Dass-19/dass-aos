---
id: 202610031420
type: decision
status: vigente
created: 2026-10-03
---

# ADR-001: Plantilla de Architecture Decision Record

> Decision: Todo cambio de alcance arquitectónico, nueva tecnología o excepción a políticas de seguridad debe registrarse como ADR inmutable bajo `.aos/decisions/` (o `decisions/` en el motor).

## Contexto
Los agentes y los humanos necesitan una fuente auditable de las decisiones que dan forma al sistema.

## Consecuencias
- A favor: trazabilidad, onboarding rápido, menos discusiones repetidas.
- En contra: pequeño overhead de documentación (mitigado por la plantilla y el rol Architect).

## Condiciones de Revocación
Solo puede ser supersedido por otro ADR que lo declare explícitamente.
