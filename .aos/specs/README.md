# Especificaciones del Proyecto (PRD / TRD)

Aquí viven los **requisitos** de una funcionalidad, antes y por encima de su implementación.

| Documento | Responde a | Lo revisa |
|---|---|---|
| `NNN-<slug>.prd.md` | **PRD** — ¿qué problema resolvemos y para quién? ¿cómo sabemos que funcionó? | negocio / producto |
| `NNN-<slug>.trd.md` | **TRD** — ¿cómo se construye y por qué así? | ingeniería |

El PRD y el TRD de una misma funcionalidad **comparten el número `NNN`**, igual que el `NNN-<slug>.design.md` de la skill `phased-delivery`.

## Cadena completa

```
PRD → TRD → contratos (.aos/contracts/) → plan (.aos/plans/active/)
```

- `aos spec new prd --title "..."` crea el PRD y le asigna número.
- `aos spec new trd --title "..."` reutiliza el número del PRD que tenga el mismo título.
- El plan enlaza su PRD y su TRD; la Fase 1 ("Discovery & contratos") es donde se escriben.
- El hook `pre-task.md` exige PRD y TRD antes de escribir contratos cuando el cambio es de producto.

## Reglas

1. **La spec se cita, nunca se parafrasea.** Los handoffs a subagentes y el `.design.md` apuntan a la ruta y a la sección del PRD/TRD. Reformular el requisito con otras palabras es un defecto.
2. **Sin criterios de aceptación medibles no hay TRD.** Un PRD sin CA-1/CA-2 verificables es una idea, no un requisito.
3. **Vía corta.** Un cambio pequeño y comprendido (según el criterio de riesgo de `phased-delivery`) no necesita PRD: se decide y se dice. El PRD es para lo que tiene alcance de producto.
4. **El PRD sobrevive al plan.** Cuando el plan se archiva, el PRD y el TRD se quedan: son la memoria de por qué existe ese código.

Estos archivos son del proyecto: `aos sync` no los toca. Las plantillas de `aos spec new` viven en `.aos/specs/templates/`.
