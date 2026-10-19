---
id: 202610191740
type: decision
status: vigente
created: 2026-10-19
---

# ADR-007: Capa de requisitos (PRD → TRD) y grafo de código por defecto

## Contexto
El motor saltaba de "petición del usuario" al plan y a los contratos sin ningún artefacto intermedio de requisitos. `grep -i "prd\|trd"` en el repo no encontraba nada: el *qué* y el *por qué* de una funcionalidad vivían solo en el mensaje original, y el plan de fases (`.aos/plans/active/`) mezclaba el objetivo de negocio con las tareas de implementación. Cuando la sesión se reanudaba días después, el criterio de aceptación había que reconstruirlo leyendo el diff.

Dos referencias externas estudiadas (2026-10-19) coinciden en formalizar esta capa:
- **Harness²** (`google-research/harness2`): el componente de harness se edita *contra evidencia conductual*, y la evidencia no es el objetivo de negocio; separar ambos evita que el agente "adivine lo que quiere el evaluador".
- **Gentle-AI** (`Gentleman-Programming/gentle-ai`): el documento de feature guarda la spec **verbatim** y cada handoff apunta a él en lugar de parafrasearlo. Su medición: con handoffs parafraseados, 73 líneas de spec y 26 comprobaciones ocultas quedaron en 23/26 tras dos rondas de feedback; pasando la spec por referencia, pasaron a la primera.

Además, el proyecto solo declara un servidor de grafo (`codebase-memory`) en `.aos/mcp-config.json`, y los hooks nombran sus herramientas (`search_graph`, `query_graph`, `index_repository`). Se evaluó **CodeGraph** (`codegraph-ai/CodeGraph`) como alternativa o añadido.

## Decisión
1. **Nueva capa de requisitos en `.aos/specs/`.** Dos documentos por funcionalidad: `PRD` (problema, usuario, alcance, criterios de aceptación medibles, no-objetivos) y `TRD` (arquitectura, contratos afectados, modelo de datos, ADRs, riesgos, plan de test y observabilidad).
2. **Nomenclatura compartida con el plan.** `NNN-<slug>.prd.md` y `NNN-<slug>.trd.md` usan el mismo contador `NNN` que `NNN-<slug>.design.md` (skill `phased-delivery`), para que los tres artefactos de una misma funcionalidad se agrupen por número.
3. **Comando propio:** `aos spec new prd|trd --title "<título>"`, con el mismo patrón que `aos plan new` (plantillas en `dass_aos/templates/specs/`, módulo `dass_aos/specs.py`).
4. **Cadena formal:** PRD → TRD → contratos (`.aos/contracts/`) → plan (Fase 1 "Discovery & contratos"). El plan enlaza PRD y TRD en su frontmatter y en su Fase 1; el hook `pre-task.md` exige PRD y TRD antes de escribir contratos cuando el cambio es de producto. Un cambio pequeño mantiene la "vía corta" que ya define `phased-delivery`.
5. **La spec se cita, nunca se parafrasea.** Los handoffs a subagentes y el `.design.md` apuntan al PRD/TRD por ruta y número de sección. Reformular el requisito con otras palabras es un defecto, no un resumen.
6. **El servidor de grafo por defecto sigue siendo `codebase-memory`.** CodeGraph **no** se añade a `.aos/mcp-config.json` ni a las instrucciones de los agentes: con 128 estrellas, funciones clave tras licencia Pro y ~1,5 GB de RAM para embeddings, no es un default responsable. Queda documentado como opción en `docs/CODE-GRAPH-OPTIONS.md`.
7. **Los hooks y las plantillas de plan siguen siendo del proyecto** (ADR-006 §7). Para recibir las plantillas nuevas, un proyecto existente borra el archivo y ejecuta `aos init`.

## Alternativas descartadas
- **PRD/TRD dentro de `.aos/plans/`:** el plan es el "cómo" y caduca al cerrarse; el PRD es el "qué" y sobrevive al plan. Mezclarlos obliga a archivar el requisito junto con la implementación.
- **PRD/TRD junto a `.aos/contracts/`:** los contratos son la interfaz técnica verificable (OpenAPI/CloudEvents), no el requisito de negocio ni la decisión de arquitectura.
- **Reemplazar `codebase-memory` por CodeGraph:** CodeGraph aporta dos cosas que el proyecto necesita (verificación diseño↔código con `verify_design`/`design_gaps` y análisis de PR con `pr_context`), pero `codebase-memory` gana en madurez (v0.12.1, ~46,9k★, actualizado a diario), lenguajes (162 frente a 38), coste de setup (un binario, sin modelo de embeddings) y honestidad de benchmarks (publica 83 % de calidad frente a 92 % del método por archivos). Añadirlo ahora duplicaría indexación y superficie de herramientas.
- **Un único documento "SPEC" que haga de PRD y TRD:** el PRD lo revisa negocio y el TRD lo revisa ingeniería; juntos, ninguno de los dos se lee entero.

## Consecuencias
- A favor: el criterio de aceptación queda escrito antes de tocar código y es lo que el plan cita; el riesgo de "parafrasear el requisito" desaparece; `aos refresh` puede listar las especificaciones abiertas.
- A favor: no se añade ninguna dependencia ni servidor; `codebase-memory` sigue siendo el único MCP de grafo.
- En contra: una tarea más de escritura antes de implementar. La vía corta de `phased-delivery` y el criterio de tamaño por riesgo (ADR-008) evitan que un cambio pequeño pague este coste.
- En contra: los proyectos existentes no reciben las plantillas de plan ni los hooks nuevos con `aos sync`; hay que borrarlos y ejecutar `aos init`.

## Condiciones de Revocación
Solo puede ser supersedido por otro ADR que lo declare explícitamente.
