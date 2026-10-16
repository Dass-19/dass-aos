---
id: 202610161312
type: plan
status: done
priority: high
tags: [plan/feature, plan/meta]
created: 2026-10-16
---

# Plan: Feature — entrega por fases, revisión adversarial y verificación en vivo en el motor

> Objetivo (Definition of Done):
> - `aos init` y `aos sync` instalan en cualquier proyecto el rol `adversarial-verifier` y las skills `phased-delivery`, `adversarial-review` y `live-verify`. Son genéricas: lo propio de cada proyecto (lentes, gates, entorno desechable, anchos de pantalla, scripts de escritorio) va en su `.local.md`.
> - Las plantillas de plan llevan un gate por fase. El bloque gestionado y los hooks remiten a las tres skills.
> - `aos refresh` avisa si falta `playwright-cli` en un proyecto con frontend web.
> - Prueba real en este repo: `live-verify` por la vía CLI y `adversarial-review` sobre el diff del plan.
> - Convalidado contra cms-crai, password-manager y finDass: no se pierde nada genérico de sus versiones y lo propio de cada uno cabe en un `.local.md`.

## Contexto y Archivos Afectados
- **Origen.** Flujo que ya ha funcionado en tres proyectos y que se generaliza en el motor.
  - **password-manager.** Origen del patrón y de la vía de escritorio.
    - Specs: `.aos/skills/specs/{phased-delivery,adversarial-review,visual-qa-egui}.md`.
    - Roles: `.aos/agents/{adversarial-verifier,visual-qa}.md`.
    - Gotchas: `qa-visual-windows-sin-robar-foco.md` y `agentes-sendmessage-duplica-agente-workflow.md`.
  - **cms-crai.** La versión más madura, usada en los planes 001–008.
    - Gates con comandos exactos, base QA desechable y verificador con `disallowedTools`.
    - Navegador con `playwright-cli` a 1400/375 px, con evidencia en `.playwright-cli/`.
    - Gotcha `playwright-cli-sesion-compartida-y-barras-ocultas.md`.
  - **finDass.** Vía web ligera: dev server, sesión firmada localmente, `playwright-cli` y la evidencia escrita en el plan (plan 007).
  - **cms.** Versión anterior de cms-crai. Su `knowledge/contract.md` tiene las reglas de origen:
    - Resolución 42: Playwright headless para QA visual.
    - Resoluciones 54–55: gana la medición; una captura en movimiento no prueba un estado.
    - Resoluciones 67–69: una prueba tiene que verse fallar.
- **Patrón común:**
  - Plan con Definition of Done, fases atómicas con gate y Discovery Trail.
  - Revisores por lente → un verificador por hallazgo que intenta refutarlo (en caso de duda, falso) → un único agente corrige solo lo confirmado → se repiten los gates.
  - Verificación en vivo con ≤3 rondas de pulido.
  - La evidencia se escribe en el plan (conteos, comandos, hallazgos con id y qué se hizo con cada uno).
  - Commit solo cuando lo pide el usuario.
- **playwright-cli** (`@playwright/cli`, 0.1.22 instalado globalmente en esta máquina; documentación revisada el 2026-10-16 en playwright.dev/agent-cli).
  - Es headless por defecto.
  - Comandos: `open`, `goto`, `snapshot`, `click`, `fill`, `type`, `eval`, `screenshot`, `resize`, `console`, `requests`, `state-save`/`state-load`, `tracing-*`, `video-*`, `close`.
  - Sesiones con `-s=<nombre>`.
  - Configuración en `.playwright/cli.config.json` (o `--config`).
  - Skill oficial: `playwright-cli install --skills [-g]` (`=claude` → `.claude/skills`, `=agents` → `.agents/skills`).
- **Archivos previstos:**
  - `dass_aos/templates/agents/adversarial-verifier.md` y `dass_aos/templates/skills/specs/{phased-delivery,adversarial-review,live-verify}.md`.
  - `dass_aos/templates/agents/{app-builder,qa-tester,reviewer}.md` y `dass_aos/templates/hooks/{pre-task,post-task}.md`.
  - `dass_aos/templates/plans/templates/*.md`.
  - `dass_aos/sync.py` (bloque gestionado), `dass_aos/memory.py` (diagnóstico) y `dass_aos/bootstrap.py` (`.gitignore`).
  - `tests/test_sync.py`, `tests/test_memory.py`, `tests/test_init.py` y `README.md`.
  - `.aos/decisions/ADR-006-*.md`.
- **ADRs vinculados:** ADR-003 (motor base + `.local.md`), ADR-004/005 (los adaptadores nativos recogen los roles y skills nuevos sin cambios). Nuevo ADR-006.
- **Gotchas a considerar:** `templates-fuera-del-paquete.md`, `windows-cp1252-encoding.md`, `claude-code-tools-allowlist.md` (el verificador sin `edit`/`write` tiene que conservar los MCP).
- **Fuera de alcance:**
  - Suites `@playwright/test` (los tres proyectos usan exploración con el CLI y cms-crai las descartó explícitamente).
  - Copiar la skill oficial de playwright-cli en el motor.
  - Playwright MCP.
  - Los adaptadores nativos (plan 003).
  - Modificar los repos de referencia sin aprobación expresa.

## Fases de Ejecución Atómica
- [x] Fase 1: ADR-006 "Flujo de entrega del motor".
  - Qué registra:
    - Núcleo genérico en el motor y lo propio de cada proyecto en `.local.md`.
    - Un solo rol nuevo (`adversarial-verifier`).
    - El bucle de autocorrección lo ejecuta quien implementa (`app-builder`); `qa-tester` solo verifica y reporta.
    - El navegador = exploración con `playwright-cli` y su skill oficial instalada globalmente; nada de suites `@playwright/test`.
    - El escritorio = scripts del proyecto o el control de escritorio de la herramienta, si lo tiene.
    - Entorno desechable obligatorio.
  - Gate: el ADR enlaza las fuentes de los tres proyectos y la documentación de playwright-cli.
- [x] Fase 2: Rol `adversarial-verifier` (`templates/agents/`).
  - Contenido:
    - Misión: refutar.
    - Cómo trabajar: reproducir el escenario siguiendo el flujo real; buscar la guarda que ya existe, el camino inalcanzable, la prueba que ya lo cubre o el comportamiento real de la librería (context7); comprobar barato y sin escribir nada.
    - Salida JSON: `is_real`, `reasoning` con `archivo:línea` y `adjusted_fix`.
  - `tools_allowed: ["read", "search", "shell", "mcp:codebase-memory", "mcp:context7"]`. La prohibición de escribir y de ejecutar lo que modifica datos va en `constraints`.
  - Gate: `aos sync` valida `tools_allowed`; el test `test_engine_docs_have_name_and_description` pasa con el rol nuevo.
- [x] Fase 3: Skill `adversarial-review.md`.
  - §1 Lentes genéricas, una por revisor y solo las que el cambio afecta:
    - Correctitud y pérdida de datos.
    - Seguridad (`knowledge/security.md`).
    - Contratos (`.aos/contracts/` y costuras cliente↔servidor).
    - Rendimiento.
    - UX/diseño, si hay UI.
    - Infraestructura y configuración, si hay.
  - Formato de cada hallazgo: `title`, `file`, `line`, `severity`, `description`, `failure_scenario`, `suggested_fix`. Solo defectos reales con escenario.
  - §2 Un `adversarial-verifier` por hallazgo; en caso de duda, falso.
  - §3 Un único `app-builder` corrige solo lo confirmado. Cada corrección deja una comprobación vista fallar con el código anterior; se repiten los gates.
  - §4 Informe:
    - Confirmados, refutados con una línea de por qué, y pendientes (al plan).
    - Gotchas nuevos.
    - Si un hallazgo contradice una skill, se corrige la skill.
  - Vía corta: para un cambio pequeño, una sola lente.
  - Orquestación: subagentes en paralelo; con opt-in a workflows, `pipeline()` de revisión → verificación.
  - El `.local.md` añade lentes con su "qué buscar" y los límites (suites destructivas, base real).
  - Gate: la spec cubre las secciones de las versiones de cms-crai y password-manager (tabla de equivalencias en el Discovery Trail).
- [x] Fase 4: Skill `phased-delivery.md`.
  - §0 Arranque: `aos refresh`, gotchas del área, y línea base antes de tocar nada (`aos verify` y los gates del proyecto), anotando lo que ya falla.
  - §1 Hasta 3 exploradores de solo lectura con áreas distintas.
  - §2 Decisiones del usuario: 2–4 opciones con la recomendada primero; lo que tiene un valor razonable por defecto se decide y se dice; se anota en el Discovery Trail.
  - §3 Plan y diseño:
    - `aos plan new` + `NNN-<slug>.design.md` como contexto compartido entre agentes.
    - ADRs para las decisiones transversales.
    - Esperar aprobación.
  - §4 Implementación:
    - Orden por dependencias.
    - Una fase no empieza sin que la anterior pase sus gates.
    - Solo en paralelo con archivos disjuntos, tras una fase "esqueleto" si hace falta.
    - El contrato se congela antes de las capas que lo consumen.
  - §5 Gates: `aos verify` + los gates del proyecto (`.local.md`) + las migraciones dos veces (la segunda no hace nada) + lógica nueva con una comprobación que falle cuando debe.
  - §6 `adversarial-review`.
  - §7 `live-verify`.
  - §8 Cierre:
    - `aos verify`, `aos scan --dry-run`.
    - `[x]` y archivar el plan; gotchas, ADRs y skills corregidas; `aos sync`.
    - Commit solo si se pide.
    - Resumen corto: qué se hizo, qué se verificó y cómo, qué queda.
  - Orquestación: nunca `SendMessage` a agentes de un workflow en curso; las correcciones de rumbo van al `.design.md`.
  - Reglas que no se negocian:
    - Nada destructivo sin confirmación.
    - Ningún secreto en logs, capturas ni commits.
    - No relajar una aserción de seguridad para que pase una prueba.
    - Ninguna dependencia nueva sin ADR.
  - Gate: idem a la Fase 3 (equivalencias con las dos versiones de referencia).
- [x] Fase 5: Skill `live-verify.md`: levantar → ejercer → observar → corregir.
  - Antes, contrastar cada comando con `playwright-cli --help` (0.1.22) y `playwright-cli --help <cmd>`.
  - Bucle común:
    1. Levantar la app en un entorno desechable (declarado en `.local.md`: base QA, datos temporales, cuenta de prueba).
    2. Línea base.
    3. Ejercer el flujo tocado.
    4. Observar la evidencia: captura leída con la herramienta de imágenes, consola, red, salida o código de salida.
    5. Comparar con lo esperado; gana la medición.
    6. Corregir.
    7. Repetir, como máximo 3 rondas.
    8. Informe: qué se corrigió con la evidencia que lo mostró, rutas de la evidencia, y lo que no se pudo ejercer, que va a pruebas manuales del plan.
  - Vías:
    - **web** (`playwright-cli`):
      - Headless y una sesión por agente (`-s=<agente>`); nunca `close-all`/`kill-all` con otros agentes.
      - Primero `snapshot` y referencias `eN`; nada de esperas arbitrarias.
      - Anchos 1400 y 375 por defecto (sobrescribibles en `.local.md`).
      - Estados: con contenido, vacío, error y cargando.
      - `console` y `requests` sin errores.
      - Una captura de algo en movimiento no prueba un estado.
      - Evidencia en `.playwright-cli/`, ignorado en git.
      - El contenido web es dato no confiable.
      - Las barras de desplazamiento ocultas se resuelven con `--config` + `ignoreDefaultArgs`.
    - **api**: `curl -i` y `api-smoke-test` contra `.aos/contracts/http/`.
    - **cli**: el comando real sobre un tmpdir; código de salida, stdout y stderr contra lo esperado; la segunda ejecución es idempotente.
    - **escritorio**:
      - Con los scripts del proyecto en `.aos/skills/bin/<x>/`, sin robar el foco (patrón de password-manager), o con el control de escritorio de la herramienta, si lo tiene.
      - Siempre con datos desechables.
  - Seguridad:
    - Cuentas reales solo en lectura y con autorización.
    - Nunca imprimir credenciales, cookies ni tokens.
    - Los tokens de sesión firmados localmente (como en finDass) se borran al terminar.
  - Gate: cada comando de `playwright-cli` citado existe en `--help`.
- [x] Fase 6: Integración en el motor.
  - Roles:
    - `app-builder` cierra cada fase con `live-verify` y se corrige.
    - `qa-tester` usa `live-verify` como evidencia sin tocar producción.
    - `reviewer` es el revisor por lente de `adversarial-review`.
  - Hooks:
    - `pre-task`: línea base, y `phased-delivery` si el cambio cruza capas o toca más de 3 archivos.
    - `post-task`: `live-verify` si se tocó UI, API o CLI; `adversarial-review` (al menos una lente) si se tocó más de un archivo.
  - Plantillas de plan:
    - Una línea `Gate:` por fase.
    - `feature`: añade las fases "Revisión adversarial" y "Verificación en vivo".
    - `bugfix`: "reproducir en vivo / ver fallar la prueba" antes del fix.
  - Bloque gestionado (`sync.py`): los pasos "En tarea" y "Post-tarea" remiten a las tres skills.
  - `aos init` añade `.playwright-cli/` a `.gitignore`, igual que hace con `.aos/native/`.
  - Gate: tests de que el bloque contiene las tres skills, de que `init` ignora `.playwright-cli/` y de que el número de roles del motor es 7.
- [x] Fase 7: Diagnóstico en `aos refresh`.
  - `playwright-cli` en `missing_dependencies` solo si hay frontend web (`package.json`, `*.html` y similares; lista corta en una constante), con la pista `npm install -g @playwright/cli@latest && playwright-cli install --skills -g`.
  - Si se confirma la ruta global de cada herramienta, avisar también si falta la skill: `~/.claude/skills/playwright-cli` cuando existe `.aos/native/claude-code.json`. Verificar antes si Antigravity lee `~/.agents/skills`; si no se confirma, solo se comprueba el CLI.
  - Nunca falla.
  - Gate: tests sin frontend → sin aviso; con `package.json` y sin CLI → aviso.
- [x] Fase 8: Dogfooding en dass-aos.
  - `aos sync` para que las piezas nuevas lleguen a `.aos/`.
  - Regenerar los nativos de Claude Code con la skill `adapt-native` (el plan 003 aún no existe) y comprobar que aparecen `adversarial-verifier` y las tres skills.
  - `live-verify` por la vía CLI: `aos init` sobre un tmpdir → `aos refresh` → `aos plan new` (numeración) → `aos sync` dos veces, la segunda sin cambios.
  - `adversarial-review` sobre el diff de este plan; los hallazgos se anotan abajo.
  - Gate: `aos verify` en verde y el informe de la revisión en el Discovery Trail.
- [x] Fase 9: Convalidación con los proyectos de referencia, en solo lectura.
  - Por proyecto (cms-crai, password-manager, cms): borrador de `phased-delivery.local.md`, `adversarial-review.local.md` y `live-verify.local.md` en el scratchpad con lo propio que tenga. Si algo no cabe en `.local.md`, falta una sección genérica y se corrige la spec.
  - Prueba real de la vía web contra una app de referencia en un entorno desechable que el usuario elige al llegar a esta fase.
  - Aplicar la migración en esos repos solo con aprobación expresa. Su `adversarial-review.md` sin marcador hace que `aos sync` lo omita con el mensaje "mueve tus cambios a .local.md".
  - Gate: una tabla por proyecto (sección de origen → spec genérica o `.local.md`) sin filas huérfanas.
- [x] Fase 10: Cierre.
  - `aos verify` y `aos scan --dry-run`.
  - README:
    - Una sección "Flujo de entrega" con las tres skills y qué va en `.local.md`.
    - `playwright-cli` en Dependencias externas.
    - La nota de migración para proyectos con versiones propias.
  - Gotchas nuevos. Se suma a la versión 0.6.0. Archivar el plan.

## Registro de Preguntas y Decisiones (Discovery Trail)
- 2026-10-16 · Proyectos de referencia: cms-crai, cms y password-manager (el "proyecto del navegador" es password-manager, por su extensión y su QA de escritorio). finDass, como caso web ligero.
- 2026-10-16 · Skill de playwright-cli: instalación global (`playwright-cli install --skills -g`) más el diagnóstico en `aos refresh`. No se copia en el motor ni se instala por proyecto.
- 2026-10-16 · Alcance del bucle en vivo: web, API, CLI y escritorio.
- 2026-10-16 · Orden: este plan antes del 003. Solo añade roles y specs a `.aos/` y las plantillas, que los adaptadores recogen después; la regla de roles de Antigravity del 003 pasa a 7 roles.
- 2026-10-16 · Por defecto, sin preguntar:
  - Un solo rol nuevo. `visual-qa` de password-manager se cubre con `app-builder` + `live-verify`, y lo propio va en `.local.md`.
  - Nombre `live-verify`.
  - Anchos 1400/375 por defecto.
  - Evidencia web en `.playwright-cli/`, ignorado en git.
- 2026-10-16 · Corregido al crear este plan: `aos plan new` numeraba contando los archivos de `active/` y generó un `003` duplicado. Ahora toma el mayor `NNN-` de `active/` y `archive/` + 1 (`dass_aos/plans.py`, test en `tests/test_plans.py`).

- 2026-10-16 · Fase 5: comandos contrastados con `playwright-cli --help` 0.1.22 y ejecutados en una sesión aislada. Encontrado: `screenshot --filename` guarda relativo al cwd, no en `.playwright-cli/` (corregido en la spec y en el gotcha `playwright-cli-skill-global-por-herramienta.md`).
- 2026-10-16 · Fase 7: Antigravity no lee `~/.agents/skills` (raíz global `~/.gemini/config/`, `skills.json`): `aos refresh` comprueba la skill solo para Claude Code; para el resto basta el CLI, cuyo `--help` imprime la ruta de su `SKILL.md`.
- 2026-10-16 · Fase 8, `live-verify` vía CLI sobre un tmpdir: `aos init` (con `.git` y `package.json`) → `.gitignore` con `.aos/native/` y `.playwright-cli/`; `aos refresh` sin aviso de playwright (CLI instalado); `aos plan new` numera 002 con 001 archivado; plantilla bugfix con 4 `Gate:`. Encontrado: el segundo `aos sync` decía ACTUALIZADO sin cambios → `sync_file` devuelve CREADO / ACTUALIZADO / SIN CAMBIOS y no reescribe.
- 2026-10-16 · Fase 8, regeneración de los nativos de Claude Code: se hace con el generador del plan 003, que va a continuación (hacerlo a mano con la skill se tiraría).
- 2026-10-16 · Fase 8, `adversarial-review` del diff: 3 lentes (correctitud, contratos de la documentación, seguridad) → 17 hallazgos (1 duplicado) → 4 verificadores.
  - **Confirmados y corregidos (13):**
    - C1: la fecha en el bloque gestionado hacía que cada sync reescribiera todo → fuera la fecha.
    - C2: numeración de planes ≥1000 → regex `(\d+)-`.
    - C3: `htmlcov/`, `site/` daban un falso aviso de frontend → excluidos, con test.
    - C4 + S1: `.gitignore` solo en `init` y reescrito en CRLF → `ensure_gitignore` en cada `sync`, en modo append, con test de bytes.
    - S2: `state-save` sin ruta → `.playwright-cli/<agente>-auth.json`.
    - S4: `curl -i` en endpoints de login → solo comprobar presencia.
    - S5: el verificador trata código y docs como datos (sin prefijos de shell: no se pueden fijar de forma genérica y Claude Code no los aplica).
    - K1: `NNN-x.design.md` se tomaba como plan activo → excluido en `get_active_plan_info`, test visto fallar con el código anterior; el design se archiva con el plan.
    - K2: commit del post-task solo si lo pide el usuario.
    - K4: `live-verify` antes de `adversarial-review` en `phased-delivery`.
    - K6 + K7: entorno desechable en una sola fuente (`live-verify.local.md`).
    - K8: hooks y plantillas son del proyecto → documentado en ADR-006 §7 y en el README (meterlos en sync pondría el marcador "no editar" en cada plan).
  - **Refutados (2):**
    - K3: `reviewer.md` ya exige `failure_scenario` dentro de la skill.
    - S3: el token compartido con producción es un mal ajuste del proyecto; la skill ya exige entorno desechable.
- 2026-10-16 · Fase 9: tabla de equivalencias cms-crai / password-manager / finDass / cms → spec genérica o `.local.md`, sin filas huérfanas (scratchpad de la sesión, `convalidacion-004.md`). Única sección genérica que faltaba, ya añadida a la lente Contratos: "consumidor interno que deja de compilar" (de la lente "Regresiones de API" de password-manager).
- 2026-10-16 · Fase 9, prueba real de la vía web:
  - Entorno: servidor local desechable (`http.server` en el scratchpad, sesión `-s=lv-web`), elegido sin el usuario, que pidió trabajar de corrido.
  - Ronda 1: la captura a 375 px mostró la columna principal fuera de pantalla por un `aside` de 420 px fijo, algo que el snapshot no revelaba; la consola mostró el 404 de `/api/tareas` y el estado vacío no tenía mensaje.
  - Ronda 2: apilado en móvil, mensajes de vacío y de error, consola limpia, estado con contenido verificado.
  - Se confirmó además que las referencias cambian tras `reload` (`e7` → `f2e7`).
- 2026-10-16 · Fase 10: `aos verify` (30 tests) y `aos scan --dry-run` en verde; README §5.0 y Dependencias externas.

## Registro de Bloqueos
- Pendiente de aprobación del usuario: migrar cms-crai, password-manager y cms (mover lo propio de sus `adversarial-review.md` / `phased-delivery.md` / `visual-qa-egui.md` a `.local.md` y dejar que `aos sync` instale las genéricas). No se tocaron.
