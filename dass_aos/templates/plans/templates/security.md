---
id: {{YYYYMMDDHHmm}}
type: plan
status: active
priority: high
tags: [plan/security]
created: {{YYYY-MM-DD}}
---

# Plan: Security — {{SHORT_TITLE}}

> Objetivo (Definition of Done): El riesgo identificado está mitigado, los scanners pasan (o existe ADR de excepción) y el cambio está documentado.

## Contexto
- Riesgo / CVE / hallazgo:
- Superficie afectada: []
- ADRs de excepción (si aplica): []
- PRD/TRD: **no aplica**; la mitigación y su justificación van en este plan y en el ADR de excepción.

## Fases
- [ ] Fase 1: Reproducir / confirmar el hallazgo (Semgrep, Checkov, manual, `live-verify` contra el entorno desechable)
  - Gate: evidencia del riesgo anotada aquí
- [ ] Fase 2: Diseñar mitigación (ADR si cambia política)
  - Gate: mitigación aprobada
- [ ] Fase 3: Implementar
  - Gate: test que reproduce el ataque y falla antes del fix
- [ ] Fase 4: Re-scan + tests + lente de seguridad de `adversarial-review`
  - Gate: scanners y tests en verde (o ADR de excepción)
- [ ] Fase 5: Cierre (knowledge/security.md, gotchas, sync)

## Discovery Trail / Bloqueos
-
