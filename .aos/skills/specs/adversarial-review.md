---
id: 202610161402
type: skill-spec
status: evergreen
cost: on-demand
name: "adversarial-review"
description: "Revisión con recibo: se congela el candidato, se elige la profundidad por tier de riesgo (0 lentes / 1 lente / 4R), cada lente busca defectos reales con escenario y cada hallazgo se intenta refutar contra el código antes de corregirlo. Una sola corrección acotada y un acuse final. Úsala al cerrar un cambio con riesgo nombrado (datos, seguridad, contratos compartidos, concurrencia, entrega), antes de dar una fase por terminada, o cuando pidan 'revisa esto', 'audita', 'busca bugs' o 'está listo'."
runtime: agent
entrypoint: "instrucciones para el agente (sin comando)"
inputs:
  - name: scope
    type: string
    description: "Qué revisar: el diff actual (git status/diff), una carpeta o una fase del plan activo"
    required: true
outputs:
  format: "recibo de revisión (candidato congelado + tier + lentes) + hallazgos confirmados/refutados + corrección aplicada y verificada"
created: 2026-10-16
---

<!-- DASS-AOS-GENERATED: no editar; agregados del proyecto en adversarial-review.local.md -->

# Skill: adversarial-review

> Los fallos que las pruebas no ven suelen estar en las costuras: un campo que se pinta pero no viaja, un permiso que solo existe en el botón, un secreto que acaba en un log. Esta revisión los busca con un revisor por lente y descarta los falsos positivos antes de tocar nada.
>
> **La revisión pertenece a una versión concreta del código.** Por eso lo primero no es leer: es congelar el candidato. Lo que se revisa después es exactamente lo que se entrega (ADR-008).

## 0. Recibo: congelar el candidato

Antes de que nadie lea el diff, anotar en el plan activo (`.aos/plans/active/`) fuera de la lista de fases:

```markdown
## Recibo de Revisión (RDD)
- Candidato: <hash> · <N> archivos · <fecha y hora>
- Archivos: `ruta/a`, `ruta/b`, ...
- Tier: pasivo | medio | alto (riesgo nombrado: ...)
- Lentes: 0 | 1 (`<lente>`) | 4R
```

Cómo obtener el `hash` sin tocar el árbol de trabajo:

```bash
git stash create                                  # hash del árbol de trabajo como commit (no modifica nada)
git status --porcelain                            # lista de archivos; incluye los no rastreados que `stash create` ignora
git diff --binary | git hash-object --stdin       # alternativa cuando no hay nada rastreado aún
```

- Si `git stash create` no devuelve nada (árbol limpio), el candidato es `HEAD`: usar `git rev-parse HEAD`.
- **Los archivos no rastreados no entran en `git stash create`**: por eso la lista de archivos se anota a mano a partir de `git status --porcelain`.
- Si el árbol cambia después del recibo (una corrección, un rebase, un pull), **el recibo se reabre**: se congela un candidato nuevo y se vuelve a empezar. La evidencia de un candidato no vale para otro.

## 1. Tier de riesgo: cuánta revisión

El tier se decide por el **riesgo del candidato congelado**, nunca por el número de archivos ni por lo que parezca el diff:

| Tier | Cuándo | Profundidad |
|---|---|---|
| **Pasivo** | Sin riesgo nombrado: texto, documentación, renombrado, formato, un cambio cuyo peor fallo es visible en el primer minuto | **0 lentes**: relectura estructural del diff y gates en verde |
| **Medio** | Lógica de negocio sin datos críticos, UI con estado, una integración nueva sin contrato compartido | **1 lente**, la que más le afecte |
| **Alto** | Datos (migración, borrado, pérdida), seguridad, contratos compartidos, concurrencia, entrega, o no existe test que atrape la regresión | **4R** (Risk, Resilience, Readability, Reliability) y verificador independiente |

Riesgo nombrado y tier deben quedar escritos en el recibo. Si dudas entre dos tiers, el alto es el barato.

## 2. Lentes (solo las del tier)

Hay un revisor por lente, y solo se lanzan las lentes del tier. Cada revisor lee el diff, **los archivos completos que toca** y la documentación de dominio de su área (`.aos/knowledge/`).

**Las 4R** agrupan el catálogo de lentes:

| R | Pregunta | Lentes del catálogo que la cubren |
|---|---|---|
| **Risk** | ¿Qué se pierde o se corrompe si esto falla? | Correctitud y pérdida de datos · Seguridad · Contratos |
| **Resilience** | ¿Qué pasa bajo error, reintento, concurrencia o carga? | Rendimiento · Infraestructura y configuración · manejo de errores |
| **Readability** | ¿Se entiende sin el autor delante? | nombres, límites de módulo, duplicación que ya divergió |
| **Reliability** | ¿Se puede comprobar y observar? | tests que atrapan la regresión · Observabilidad (log/métrica de frontera) |

Catálogo de lentes, para el tier medio y para concretar las 4R:

| Lente | Qué busca |
|---|---|
| Correctitud y pérdida de datos | orden de operaciones; estado viejo o carreras; una migración que pisa datos o que no es idempotente; un borrado sin confirmar; un error tragado; un caso límite (vacío, duplicado, límite, zona horaria, codificación) |
| Seguridad | todo lo que exige `.aos/knowledge/security.md`; entrada sin validar en una frontera de confianza; permiso comprobado solo en el cliente; inyección (SQL, shell, ruta); secretos en logs, mensajes, capturas o commits; datos privados que salen por la API |
| Contratos | endpoints, eventos o esquemas fuera de `.aos/contracts/`; una clave que el servidor sirve y el cliente no lee, o al revés; una variante nueva en un solo lado; un cliente generado sin regenerar; un consumidor interno (otro módulo, binario o paquete) que deja de compilar o de funcionar con la firma nueva |
| Rendimiento | trabajo repetido en un bucle, render o petición; E/S en el hilo de UI; consultas N+1; recursos que no se liberan |
| UX y diseño (si hay UI) | un estado vacío, de carga o de error sin resolver; una acción sin confirmación o sin mensaje; un error lejos de su campo; un control inalcanzable con teclado; desbordes en móvil; contraste |
| Infraestructura y configuración (si la hay) | una variable que no llega al proceso; un puerto o permiso de más; una ruta no enrutada; un recurso cargado de un CDN sin decidirlo; finales de línea; rutas absolutas no portables |

El proyecto añade lentes o concreta qué buscar en `adversarial-review.local.md`.

Formato de cada hallazgo: `title`, `file`, `line`, `severity` (critical / high / medium / low), `description`, `failure_scenario` (entrada o estado concreto → resultado incorrecto) y `suggested_fix`.

**Solo defectos reales con escenario.** Nada de estilo ni de "sería más limpio". Si no hay nada, la lista va vacía.

## 3. Verificación adversarial (solo tier alto; nunca el modelo que escribió el cambio)

- Un verificador independiente por hallazgo intenta **refutarlo** leyendo el código, quién lo llama, las pruebas y, si depende de una librería, su documentación (context7) o su fuente instalada.
- Si es especulativo, ya está cubierto o no se puede alcanzar → `is_real: false`. **En caso de duda, false.**
- Si se puede comprobar barato y sin alterar datos, se comprueba.
- Devuelve `is_real`, `reasoning` con `archivo:línea` y, si la severidad o la solución no encajan, `adjusted_fix`.

En tier medio, la verificación la hace el mismo agente que revisó, con el mismo criterio: en caso de duda, `false`.

## 4. Una sola corrección acotada

- **Una pasada.** Se aplican únicamente los hallazgos confirmados, con `adjusted_fix` cuando exista. Si dos correcciones chocan, se combinan y se explica.
- Cada corrección de lógica deja una comprobación que la habría detectado, **vista fallar con el código anterior**: una aserción en la suite que corresponda, o el comando exacto con su salida esperada.
- Se repiten los gates de `phased-delivery` §5 y, si el cambio tocó UI, API o CLI, `live-verify`.
- Lo que no se arregló en esta pasada **no se arregla a medias**: se anota como pendiente con su motivo. Una segunda ronda de revisión sobre el mismo candidato ya es un candidato nuevo (volver al paso 0).

## 5. Acuse final

Se anota en el plan, bajo el recibo, y cierra la transacción:

```markdown
### Acuse
- Candidato revisado: <hash> · tier <pasivo|medio|alto> · lentes <0|1|4R>
- Confirmados: <n> (severidad y `archivo:línea` de cada uno)
- Refutados: <n> (una línea con el porqué)
- Corrección: <qué se cambió> · gates repetidos: <comando> → verde
- Pendientes: <n> → anotados en el plan con su motivo
- Documentos corregidos: <skill, gotcha o ADR que el hallazgo dejó obsoleto>
```

- Los pendientes van al plan activo de `.aos/plans/active/` y las trampas nuevas a `.aos/knowledge/gotchas/`.
- Si un hallazgo confirmado contradice una skill o un documento de `.aos/knowledge/`, **se corrige ese documento** en la misma pasada.
- Lección con evidencia (comando o salida) → una fila en `.aos/knowledge/lessons/LEDGER.md`.

## Orquestación

- Los revisores van en paralelo con la herramienta de agentes de tu entorno, y después un verificador por hallazgo. Si el usuario aceptó usar workflows, un `pipeline()` de revisión → verificación permite verificar cada lente en cuanto termina.
- Delegar aquí tiene un motivo nombrable: **verificador independiente** (tier alto, nunca el autor) y **lentes en paralelo** (≥ 2 lentes con superficie disjunta). Si no puedes nombrar el motivo, hazlo inline.
- Si tu herramienta no tiene subagentes, haz las lentes una a una y verifica cada hallazgo tú mismo antes de corregir nada.

## Límites

- Los revisores y el verificador no modifican archivos.
- Nadie ejecuta suites, seeds ni scripts que escriban datos para comprobar un hallazgo, salvo contra el entorno desechable que declare `live-verify.local.md` y diciéndolo.
- No se corrige nada que no esté confirmado "por si acaso".
- La revisión no hace commit, push ni entrega: eso es del usuario.
