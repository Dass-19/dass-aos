---
id: 202610161403
type: skill-spec
status: evergreen
cost: on-demand
name: "phased-delivery"
description: "Flujo por fases para cambios con riesgo nombrado (datos, seguridad, contratos compartidos, concurrencia, entrega) o poco comprendidos: explorar en paralelo, escribir PRD/TRD, decidir con el usuario, planificar en .aos/plans, implementar en orden de dependencias con gates por fase, verificar en vivo y revisar con recibo. El tamaño se decide por riesgo y comprensión, nunca por número de archivos (ADR-008). Úsala también para continuar un plan activo fase por fase."
runtime: agent
entrypoint: "instrucciones para el agente (sin comando)"
inputs:
  - name: request
    type: string
    description: "Lo que se pide (feature, rediseño, integración, migración…) o el plan activo a continuar"
    required: true
outputs:
  format: "plan en .aos/plans/active/ + código verificado + PRD/TRD, ADRs, gotchas, lecciones y skills actualizados"
created: 2026-10-16
---

# Skill: phased-delivery

> Para un cambio pequeño y comprendido basta con leer, editar, pasar los gates (§5), hacer `live-verify` si toca UI, API o CLI, y revisar con la lente que le corresponda. Este flujo es para lo que tiene riesgo.

## 0. Arranque
- `aos refresh`: gotchas recientes, especificaciones abiertas y plan activo. Lee los gotchas del área antes de diseñar.
- **Línea base antes de tocar nada:** `aos verify` y los gates del proyecto (`phased-delivery.local.md`). Anota lo que ya falla, para no confundirlo después con una regresión.
- Si se pide continuar un plan activo, sigue por su primera fase sin marcar. `aos status` dice en qué estado está: `Working`, `Checking`, `Ready` o `Needs decision`.
- Una tarea suelta que no pertenece al plan activo no queda bloqueada por él. Si es pequeña, va por la vía corta; si tiene riesgo, lleva su propio plan. Avisa al usuario si toca archivos que el plan activo también va a tocar.

## 0.5 Enrutado por riesgo (tamaño de la tarea)

El tamaño se decide por **riesgo** (datos, seguridad, contratos compartidos, concurrencia, entrega) y por lo **comprendida** que esté la tarea. **Nunca por número de archivos** (ADR-008). Un bug de tres líneas en un archivo de migración es grande; un renombrado en veinte archivos de texto es pequeño.

| Tier | Señales | Flujo |
|---|---|---|
| **Pequeño** | vía corta: sin riesgo nombrado, se entiende entera antes de editar, se puede reanudar leyendo el diff | Leer → editar → gates (§5) → `live-verify` si aplica → una lente si el cambio lo pide |
| **Medio** | varias capas, pero sin datos críticos ni contrato compartido | Este flujo sin PRD; plan corto solo si ayuda a reanudar |
| **Alto** | datos, seguridad, contratos compartidos, concurrencia, entrega, o sin test que atrape la regresión | Este flujo completo: PRD/TRD, plan con gates, `live-verify` y revisión **4R** con recibo |

**Motivos de delegación** (si ninguno se puede nombrar, trabaja **inline**):

| Motivo | Umbral |
|---|---|
| Exploración | Más de ~3 llamadas de lectura, ~10k tokens de código o más de 5 búsquedas para entender el área |
| Escritores en paralelo | ≥ 2 unidades independientes con superficie de archivos disjunta |
| Backstop de contexto | El trabajo no cabe en la ventana sin perder lo ya decidido |
| Verificador independiente | Solo con **tier alto**, y **nunca** el modelo que escribió el cambio |

## 1. Exploración en paralelo
- Hasta 3 exploradores de solo lectura, **cada uno con un área distinta** (por ejemplo: datos · lógica · interfaz), y solo si se cumple el umbral de exploración.
- Cada uno devuelve hallazgos con `archivo:línea`, piezas reutilizables y riesgos, comprobados en el código y no supuestos.

## 2. Requisitos y decisiones del usuario
- **Si tiene alcance de producto**, PRD y TRD antes de los contratos (ADR-007, skill `spec-driven`): `aos spec new prd --title "<título>"` y luego el TRD con el mismo título, que reutiliza el número. Sin criterios de aceptación medibles, no se pasa al TRD.
- Pregunta solo lo que le corresponde decidir (alcance, tecnología, diseño, algo destructivo): 2–4 opciones, la recomendada primero y con su coste.
- Lo que tenga un valor por defecto razonable no se pregunta: se decide y se dice.
- Anota cada respuesta en el *Discovery Trail* del plan. Una pregunta registrada sin `Decisión:` deja el trabajo en `Needs decision`.

## 3. Plan y diseño (rol `architect`)
1. `aos plan new feature --title "<título>"` y rellena el plan en `.aos/plans/active/NNN-*.md`: Definition of Done medible, riesgo esperado (ADR-008) y fases atómicas, **cada una con su línea `Gate:`**. Enlaza el PRD y el TRD.
2. Si van a trabajar varios agentes, escribe al lado `NNN-<slug>.design.md` con los nombres exactos de archivos, funciones y claves, las decisiones verificadas y los comandos de comprobación. Es el contexto que comparten: si algo cambia, se actualiza ahí. **El requisito se cita por ruta y sección, nunca se parafrasea** (ADR-007).
3. Un ADR en `.aos/decisions/` por cada decisión transversal nueva.
4. Presenta el plan y **espera la aprobación** antes de escribir código, salvo que el usuario haya pedido trabajar de corrido.

## 4. Implementación por fases (rol `app-builder`)
- **En orden de dependencias** (por ejemplo: infraestructura → datos → backend → interfaz). Una fase no empieza hasta que la anterior pasa sus gates.
- **Test-first**: cada regla pedida deja una comprobación RED **antes** de implementarla, y una comprobación de que el comportamiento previo que no debía cambiar sigue igual. Una prueba no vista fallar no demuestra nada.
- Un agente por fase, con el plan, el documento de diseño y la documentación de su capa.
- **En paralelo, solo con archivos disjuntos** y con el motivo de delegación nombrado. Si hace falta, una fase "esqueleto" fija antes los puntos de integración (tipos, rutas, claves) para que las fases paralelas no editen los mismos archivos.
- El contrato (`.aos/contracts/`) se fija antes de las capas que lo consumen y no cambia sin volver a esa fase.
- Cada fase deja la app funcionando, no a medias.

## 5. Gates de cada fase
Los que apliquen a lo tocado; todos deben pasar.
- `aos verify` (lint y tests de `.aos/config.json`).
- Los gates del proyecto, con sus comandos exactos, en `phased-delivery.local.md`.
- Una migración se ejecuta dos veces: la segunda no debe hacer nada.
- Cada lógica nueva no trivial deja una comprobación que **se haya visto fallar** cuando debe.
- Las suites que escriben datos se ejecutan solo contra el entorno desechable que declare `live-verify.local.md`.

## 6. Verificación en vivo
Skill `live-verify`, para cualquier cambio en UI, API, CLI o app de escritorio: levantar la app, ejercitarla, mirar la evidencia y corregir, en hasta 3 rondas.

## 7. Revisión con recibo
Va después de `live-verify` para que también se revisen sus correcciones. Skill `adversarial-review` (ADR-008):
1. **Congelar el candidato** antes de leerlo: hash del árbol y archivos que lo componen, anotados en el plan.
2. **Tier por riesgo**: pasivo (0 lentes), medio (1 lente) o alto (4R + verificador independiente).
3. Revisores por lente → un `adversarial-verifier` por hallazgo → **una sola corrección acotada** → acuse con los gates repetidos.

## 8. Cierre
- `aos verify` y `aos scan --dry-run`.
- `aos doctor` (solo diagnóstico) si se tocaron skills, roles, hooks o el bloque gestionado.
- Marca `[x]` en el plan con la evidencia: conteos, comandos y hallazgos con lo que se hizo con cada uno. Cuando estén todas las fases, mueve el plan (y su `.design.md`, si lo tiene) a `.aos/plans/archive/`. **El PRD y el TRD se quedan**: son la memoria de por qué existe ese código.
- Gotchas nuevos, ADRs, **una fila en `.aos/knowledge/lessons/LEDGER.md`** si hubo una lección con evidencia, y **las skills o documentos de conocimiento corregidos** si algo de lo que decían resultó falso.
- `aos sync` si cambiaron roles o skills, y `adapt-native` si `aos refresh` lo marca desactualizado.
- **Commit solo cuando lo pida el usuario**, uno por cambio verificado (`git-atomic-commit`, nunca `git add -A`).
- Al usuario, un resumen corto: qué se hizo, qué se verificó y cómo, y qué queda.

## Orquestación
- Sin permiso del usuario para usar workflows: subagentes con la herramienta de agentes, en paralelo solo cuando sean independientes y el motivo de delegación esté nombrado. Con permiso: un workflow por bloque, con fases secuenciales cuando dependan entre sí.
- **Nunca envíes mensajes a un agente lanzado por un workflow en curso:** se reanuda como copia duplicada y quedan dos escritores sobre el mismo árbol. Las correcciones de rumbo van al `.design.md`, que los agentes leen antes de cada fase.
- Si el usuario se ausenta, el trabajo sigue: no te detengas a esperar confirmaciones que no hacen falta.

## Reglas que no se negocian
- Nada destructivo sobre datos reales sin confirmación explícita: ni seeds, ni borrados, ni `git clean`.
- Ningún secreto en logs, mensajes, capturas ni commits.
- No se relaja una aserción de seguridad para que pase una prueba.
- No se añade una dependencia sin ADR.
- Un cambio de la spec después de existir el TRD se propaga a la spec, al TRD y al plan en la misma pasada.
