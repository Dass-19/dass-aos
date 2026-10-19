---
id: 202610191742
type: skill-spec
status: evergreen
name: "spec-driven"
description: "Cadena de requisitos antes de implementar: escribe el PRD (qué y para quién, con criterios de aceptación medibles), deriva el TRD (cómo y por qué así), declara los contratos y recién entonces abre el plan. Úsala al empezar una funcionalidad con alcance de producto, cuando pidan 'documenta esto', 'haz un PRD', 'define el alcance', o cuando el plan activo no cite PRD ni TRD."
cost: on-demand
runtime: agent
entrypoint: "instrucciones para el agente (sin comando)"
inputs:
  - name: request
    type: string
    description: "Funcionalidad o necesidad de negocio; puede venir ya como PRD a medias"
    required: true
outputs:
  format: "NNN-<slug>.prd.md + NNN-<slug>.trd.md en .aos/specs/, contratos actualizados y plan que los cita"
created: 2026-10-19
---

<!-- DASS-AOS-GENERATED: no editar; agregados del proyecto en spec-driven.local.md -->

<!-- DASS-AOS-GENERATED: no editar; agregados del proyecto en spec-driven.local.md -->

# Skill: spec-driven

> El requisitos no se recuerda entre sesiones: se escribe. Un PRD sin criterios de aceptación medibles es una idea, no un requisito; un TRD que repite el PRD no es un TRD.

## 1. Vía corta (cuándo NO usar esta skill)

No está toda funcionalidad obligada a un PRD. **No la uses** cuando el cambio es pequeño y comprendido según el criterio de riesgo de `phased-delivery` (sin datos, seguridad, contratos compartidos, concurrencia ni entrega), o cuando es un bugfix o un refactor de comportamiento idéntico: para eso están sus plantillas de plan. En ese caso decide y dilo, sin documento.

Sí la usarás cuando: hay alcance de producto, alguien de negocio tiene que aprobar el criterio de aceptación, o la funcionalidad va a vivir más que su plan.

## 2. PRD — el qué y el para quién

1. `aos spec new prd --title "<título>"` → `.aos/specs/NNN-<slug>.prd.md`.
2. Rellena el **Problema** con evidencia (incidencia, dato, coste medido). Si solo tienes una hipótesis, escríbelo como hipótesis: no la disfraces de dato.
3. **Criterios de aceptación**: cada uno comprobable con un comando, una consulta o una observación concreta. Si no sabes cómo se comprobaría, todavía no es un criterio.
4. **Fuera de alcance**: escrito, para que el TRD y el plan no crezcan solos.
5. Pregunta al usuario solo lo que le toca decidir (alcance, prioridad, algo destructivo): 2–4 opciones, la recomendada primero. Anota cada respuesta en el *Discovery Trail* del plan.

## 3. TRD — el cómo y el por qué así

1. `aos spec new trd --title "<mismo título>"` → reutiliza el NNN del PRD.
2. **Cita el PRD, no lo repitas**: referencia `NNN-<slug>.prd.md` y los CA que cubre.
3. Declara **los contratos antes de implementarlos** (ADR-001): `.aos/contracts/http/`, `.aos/contracts/events/`, `.aos/contracts/schemas/`. Si un endpoint o evento no está declarado, se declara aquí.
4. Una dependencia nueva necesita ADR antes de aparecer en el TRD.
5. Anota el **plan de prueba** y la **observabilidad**: cómo se detectaría en producción que esto falla.

## 4. Contratos y plan

- Crea o actualiza los contratos y, si aplica, `aos generate-client --contract <ruta>`.
- Abre el plan con `aos plan new feature --title "<título>"` y **enlaza PRD y TRD** en su Fase 1 ("Discovery & contratos"), en el frontmatter (`prd:`, `trd:`) y en la sección de contexto.
- Si ya hay un plan activo para esta funcionalidad, actualízalo en lugar de abrir otro.

## 5. Reglas que no se negocian

- **La spec se cita, nunca se parafrasea.** En handoffs a subagentes y en el `NNN-<slug>.design.md`, apunta a la ruta y a la sección. Reformular el requisito con otras palabras es un defecto, no un resumen.
- **Sin criterios medibles no se pasa al TRD.** Vuelve al PRD.
- Un cambio en el PRD después de que exista el TRD se propaga al TRD y al plan en la misma pasada.
- El PRD y el TRD no se borran al cerrar el plan: se quedan como memoria de por qué existe ese código.
