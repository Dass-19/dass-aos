---
id: 202610191741
type: decision
status: vigente
created: 2026-10-19
---

# ADR-008: Enrutado por riesgo y revisión con recibo (candidato congelado)

## Contexto
El motor decidía el flujo por **número de archivos**:
- Bloque gestionado (`sync.build_managed_block`): *"Si el cambio cruza capas o toca más de tres archivos, seguir la skill `phased-delivery`"*.
- Post-tarea: *"Si se tocó más de un archivo, skill `adversarial-review`"*.

Ese eje es el equivocado. Un bug de tres líneas repartido en dos archivos activaba revisión adversarial completa, y una migración de datos en un solo archivo no activaba nada. Gentle-AI (`Gentleman-Programming/gentle-ai`, ODD) lo formula explícitamente: *"Tasks are sized by understanding, risk, and resumability, never by file count"*, y lo respalda con mediciones (n=1 por celda, con suites de aceptación ocultas):
- Bug de 3 líneas en una función: 335 s · 56 turnos · $0.339 → **77 s · 10 turnos · $0.105** al trabajar inline, sin subagentes.
- Bug en lógica compartida: 479 s · $0.361 → **276 s · $0.207** con un solo explorador.
- Migración de datos (riesgo alto): con un verificador independiente pasó **a la primera ronda**.
- Un handoff parafraseado hizo fallar 13 comprobaciones; la spec pasada por referencia pasó.

Su tabla de motivos de delegación (Exploración > ~3 llamadas o ~10k tokens o > 5 búsquedas; Escritores en paralelo ≥ 2 unidades independientes con superficie disjunta; Backstop de contexto; Verificador independiente solo con riesgo alto y **nunca el modelo que escribió el cambio**) describe mejor el criterio que el conteo de archivos.

Por otra parte, la revisión adversarial existente no fijaba **qué versión** se estaba revisando: entre el momento en que un revisor leía el diff y el momento en que se aplicaba una corrección, el árbol de trabajo podía haber cambiado, y la evidencia quedaba huérfana. Gentle-AI lo resuelve con *Receipt-Driven Development* (RDD): congelar el candidato antes de leerlo y graduar la profundidad de revisión según el riesgo de ese candidato congelado.

## Decisión
1. **Se retira el conteo de archivos como eje de tamaño.** El criterio pasa a ser el **riesgo** (datos, seguridad, contratos compartidos, concurrencia, entrega) y la **comprensión** de la tarea. El criterio anterior se conserva documentado en este ADR y no se borra en silencio.
2. **Motivos de delegación con umbral**, en el bloque gestionado y en `phased-delivery`: Exploración, Escritores en paralelo, Backstop de contexto y Verificador independiente. Sin un motivo que se pueda nombrar, el agente trabaja **inline**, sin subagentes.
3. **Recibo de revisión (RDD-lite) en `adversarial-review`:** antes de que nadie lea el cambio, se **congela el candidato** anotando en el plan activo el identificador de revisión (hash del árbol o del diff) y los archivos que lo componen. La revisión y su evidencia pertenecen a esa versión exacta.
4. **Profundidad por tier de riesgo**, decidida desde el candidato congelado y no desde el juicio del modelo:
   - **Pasivo** (sin riesgo nombrado): relectura estructural, **cero lentes**.
   - **Medio**: **una lente**, la que más afecte.
   - **Alto** (datos, seguridad, contratos compartidos, concurrencia, entrega, o sin test que atrape la regresión): las **4R** — Risk, Resilience, Readability, Reliability.
5. **Máximo una corrección acotada** por candidato y **un acuse final** que cierra la transacción. El commit, el push y la entrega siguen siendo del usuario.
6. **`aos status`:** subcomando determinista que deriva el estado de los archivos en disco y lo imprime en uno de cuatro valores públicos — `Working`, `Checking`, `Ready`, `Needs decision`. Ningún modelo decide qué viene después.

## Alternativas descartadas
- **Mantener el conteo de archivos y solo añadir los motivos de delegación:** deja la regla contradictoria en el mismo documento (el conteo seguiría disparando el flujo por encima de los motivos).
- **RDD completo con máquina de estados persistente y negociación de capacidades:** es la parte de Gentle-AI que exige un binario Go con estado propio; rompe el principio de "Python stdlib puro, cero dependencias" del motor. El recibo en el plan logra el mismo efecto con archivos.
- **Congelar con `git stash` o un worktree:** altera el árbol del usuario. El hash del diff no lo toca.
- **Que el modelo decida la profundidad de revisión:** es exactamente lo que RDD evita; dos modelos eligen distinto dos días seguidos.

## Consecuencias
- A favor: los cambios pequeños dejan de pagar revisión y planificación completas; los cambios de riesgo alto reciben verificación independiente.
- A favor: la evidencia de revisión es trazable a una versión concreta y no se puede "revisar algo distinto de lo que se entrega".
- En contra: el agente tiene que nombrar el riesgo y anotar el recibo, trabajo que antes no hacía. `aos status` y el tier arrancan con valores conservadores.
- En contra: `aos status` deriva el estado de archivos y puede quedarse corto en proyectos que no usan el plan activo; se documenta como orientativo, nunca como bloqueo.

## Condiciones de Revocación
Solo puede ser supersedido por otro ADR que lo declare explícitamente.
