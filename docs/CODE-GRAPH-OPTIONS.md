# Servidores de grafo de código: opciones y decisión

> Estado: **decisión tomada el 2026-10-19** (ver [ADR-007](../.aos/decisions/ADR-007-capa-de-requisitos-y-grafo-de-codigo.md) §6).
> AOS declara **un solo** servidor de grafo: `codebase-memory`. `codegraph` **no está integrado**:
> este documento existe para que la decisión se pueda revisar con datos, no para habilitarlo.

## Qué necesita AOS de un grafo

AOS no usa el grafo como chat: lo usa **antes de modificar código**, para responder «quién llama a
esto», «qué depende de este módulo» y «qué se rompe si cambio la firma». Las herramientas que los
hooks y skills nombran hoy son tres:

| Necesidad | Herramienta nombrada en `.aos/` |
|---|---|
| Buscar símbolo por nombre o concepto | `search_graph` |
| Consulta estructural (llamadas, dependencias) | `query_graph` |
| Indexar el proyecto por primera vez | `index_repository` |

Cualquier servidor que se adopte debe cubrir esas tres, con un coste de instalación que un
desarrollador acepte en un proyecto Python de stdlib puro.

## Los dos candidatos

| | **codebase-memory** (actual) | **CodeGraph** |
|---|---|---|
| Origen | DeusData, `codebase-memory-mcp` | `codegraph-ai/CodeGraph` |
| Licencia | MIT | Apache-2.0 (con funciones tras licencia Pro) |
| Versión revisada | v0.12.1 | v0.21.0 |
| Adopción | ~46,9k ★ | ~128 ★ |
| Distribución | binario nativo en C, sin runtime extra | binario + dependencias (RocksDB, embeddings ONNX) |
| Coste en ejecución | bajo | ~1,5 GB de RAM por índice con embeddings |
| Lenguajes | 162 | 38 |
| Superficie | 17 herramientas, LSP híbrido, nodos de ruta e IaC | 42 herramientas community + 27 Pro (17 de seguridad) |
| Perfiles | — | `--profile core / graph / memory / security` |
| Extras propios | — | `verify_design`, `design_gaps`, `generate_architecture_doc`, `pr_context`, GitHub Action de PR |
| Honestidad de benchmark | Publica 83 % de calidad frente a 92 % del método por archivos | No localizado en la revisión |

## Qué aportaría cada uno

**`codebase-memory` ya es el default y no hay que cambiar nada.** Cubre las tres herramientas que
AOS nombra, indexa más lenguajes y su coste de instalación es un binario. Su punto débil es que no
tiene verificación diseño↔código ni análisis de PR.

**`CodeGraph` aporta dos cosas que AOS hoy no tiene:**

1. **`verify_design` / `design_gaps`**: comparar el diseño declarado (nuestros `.design.md` y
   contratos) con lo que el código hace de verdad. Es exactamente el tipo de comprobación
   determinista que AOS prefiere.
2. **`pr_context` y la GitHub Action**: revisión estructural automática en cada PR, con el grafo
   como fuente. Encajaría con `adversarial-review` en CI.

Lo que impide adoptarlo como default:

- **Adopción y madurez.** 128 ★ frente a 46,9k no es un benchmark, pero sí es un riesgo de
  mantenimiento y de bus factor para una herramienta que el agente usa a diario.
- **Funciones clave tras Pro.** Las 17 herramientas de seguridad y parte del análisis avanzado no
  están en la licencia Apache-2.0. Un flujo que dependa de ellas deja de ser reproducible para
  quien no paga.
- **Coste de ejecución.** RocksDB más embeddings ONNX (~1,5 GB de RAM) no es aceptable como
  requisito implícito en un proyecto que se instala con `pip install dass-aos`.
- **Duplicaría indexación.** Dos servidores de grafo sobre el mismo árbol compiten por el mismo
  presupuesto de contexto y el agente no sabe cuál creer.

## Decisión

1. **`codebase-memory` sigue siendo el único servidor de grafo** declarado en
   `.aos/mcp-config.json`. Los nombres `search_graph`, `query_graph` e `index_repository` de los
   hooks y skills **no se neutralizan**: son su API y cambiarlos rompería proyectos existentes.
2. **`codegraph` no se añade.** No es una dependencia, ni una opción documentada como «instálala y
   listo».
3. **Condición para revisar esta decisión** (cualquiera de las tres):
   - `CodeGraph` publica un benchmark reproducible de calidad y latencia sobre un corpus público.
   - Las funciones de `verify_design` / `pr_context` pasan a Apache-2.0 sin la capa Pro.
   - AOS necesita verificación diseño↔código como gate y `codebase-memory` sigue sin ofrecerla.
4. Cuando se revise, la comparación se hace **en un worktree desechable**, con el mismo repositorio
   indexado por ambos y las mismas cinco consultas (`quién llama`, `qué depende de`, `impacto de
   cambio de firma`, `rutas no enrutadas`, `diseño vs código`). El resultado se anota aquí con
   números, no con impresiones.

## Cómo se instala `codebase-memory` (recordatorio)

Ya está en `.aos/mcp-config.json`. Si `search_graph` no encuentra el proyecto, el hook
`session-start` indica ejecutar `index_repository` con su ruta:

```
index_repository(path: "<ruta del proyecto>")
```

La base de datos vive en el directorio del usuario, no en `.aos/`, así que no se versiona.
