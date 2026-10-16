---
id: 202610161402
type: skill-spec
status: evergreen
name: "adversarial-review"
description: "Revisión por lentes en paralelo (correctitud y pérdida de datos, seguridad, contratos, rendimiento, UX, infraestructura) en la que cada hallazgo se intenta refutar contra el código antes de corregirlo. Úsala al cerrar un cambio que toque más de un archivo, antes de dar una fase por terminada, o cuando pidan 'revisa esto', 'audita', 'busca bugs' o 'está listo'."
runtime: agent
entrypoint: "instrucciones para el agente (sin comando)"
inputs:
  - name: scope
    type: string
    description: "Qué revisar: el diff actual (git status/diff), una carpeta o una fase del plan activo"
    required: true
outputs:
  format: "lista de hallazgos confirmados + correcciones aplicadas y verificadas"
created: 2026-10-16
---

# Skill: adversarial-review

> Los fallos que las pruebas no ven suelen estar en las costuras: un campo que se pinta pero no viaja, un permiso que solo existe en el botón, un secreto que acaba en un log. Esta revisión los busca con un revisor por lente y descarta los falsos positivos antes de tocar nada.
> Para un cambio pequeño basta con una sola lente, la que más le afecte.

## 1. Revisores por lente (rol `reviewer`, en paralelo)

Hay un revisor por lente, y solo se lanzan las lentes a las que afecta el cambio. Cada revisor lee el diff, **los archivos completos que toca** y la documentación de dominio de su área (`.aos/knowledge/`).

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

## 2. Verificación adversarial (rol `adversarial-verifier`, uno por hallazgo)

- Intenta **refutarlo** leyendo el código, quién lo llama, las pruebas y, si depende de una librería, su documentación (context7) o su fuente instalada.
- Si es especulativo, ya está cubierto o no se puede alcanzar → `is_real: false`. **En caso de duda, false.**
- Si se puede comprobar barato y sin alterar datos, se comprueba.
- Devuelve `is_real`, `reasoning` con `archivo:línea` y, si la severidad o la solución no encajan, `adjusted_fix`.

## 3. Corrección (rol `app-builder`)

- Un solo agente aplica todos los hallazgos confirmados, con `adjusted_fix` cuando exista. Si dos correcciones chocan, las combina y lo explica.
- Cada corrección de lógica deja una comprobación que la habría detectado, **vista fallar con el código anterior**: una aserción en la suite que corresponda, o el comando exacto con su salida esperada.
- Se repiten los gates de `phased-delivery` §5 y, si el cambio tocó UI, API o CLI, `live-verify`.

## 4. Informe

- Confirmados (severidad, `archivo:línea` y qué se hizo), refutados (una línea con el porqué) y pendientes con su motivo.
- Los pendientes van al plan activo de `.aos/plans/active/` y las trampas nuevas a `.aos/knowledge/gotchas/`.
- Si un hallazgo confirmado contradice una skill o un documento de `.aos/knowledge/`, **se corrige ese documento** en la misma pasada.

## Orquestación
- Los revisores van en paralelo con la herramienta de agentes de tu entorno, y después un verificador por hallazgo. Si el usuario aceptó usar workflows, un `pipeline()` de revisión → verificación permite verificar cada lente en cuanto termina.
- Si tu herramienta no tiene subagentes, haz las lentes una a una y verifica cada hallazgo tú mismo antes de corregir nada, con el mismo criterio: en caso de duda, false.

## Límites
- Los revisores y el verificador no modifican archivos.
- Nadie ejecuta suites, seeds ni scripts que escriban datos para comprobar un hallazgo, salvo contra el entorno desechable que declare `live-verify.local.md` y diciéndolo.
- No se corrige nada que no esté confirmado "por si acaso".
