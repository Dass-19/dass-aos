# DASS-AOS: Agent Operating System

Sistema operativo y CLI stack-agnostic diseñado para estructurar, auditar y optimizar el workflow de desarrollo asistido por agentes de IA, manteniendo al desarrollador humano en el centro de las decisiones arquitectónicas y de negocio (Human-in-the-Loop).

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://python.org)
[![Platform](https://img.shields.io/badge/platform-windows%20%7C%20linux%20%7C%20macos-informational)]()
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-standard%20library%20only-orange)]()

---

## 1. Problema y Enfoque

El desarrollo con AI coding agents (Claude Code, Cursor, Windsurf, Gemini, Antigravity, Aider) presenta fricciones recurrentes en codebases complejas:

1. **Amnesia entre sesiones**: Reincidencia en bugs y trampas técnicas previamente solucionadas (gotchas).
2. **Degradación arquitectónica**: Modificación descontrolada de componentes sin consultar el dependency graph ni la arquitectura preexistente.
3. **Alucinación de interfaces**: Creación de endpoints, eventos o tipos de datos sin contratos formales.
4. **Falta de verificación sistemática**: Cierre de tareas sin validación estricta de unit tests, linters y análisis estático de seguridad (SAST).

DASS-AOS resuelve estos problemas formalizando un lifecycle disciplinado, desarrollo Contract-First y memoria persistente por proyecto, gobernado siempre bajo supervisión humana.

---

## 2. Filosofía: Human-in-the-Loop (HITL)

DASS-AOS no promueve la autonomía ciega ni busca sustituir el criterio del desarrollador. Su objetivo es **optimizar el rendimiento del agente reduciendo la sobrecarga operativa manual**, garantizando que el desarrollador conserve el control sobre:

- **Business Intent & Scope**: El humano define qué construir y establece los límites de dominio.
- **Validación de Planes y ADRs**: Los cambios estructurales transversales requieren aprobación en planes por fases y Architecture Decision Records (ADRs).
- **Supervisión de Calidad**: El agente ejecuta comprobaciones locales (linters, test suites, SAST e IaC scanners) y entrega reportes trazables antes de hacer commit o abrir un Pull Request (PR).

---

## 3. Modelo Operativo: Distribución de Responsabilidades

| Fase del Workflow | Rol del Desarrollador (Humano) | Rol del AI Agent |
|---|---|---|
| **Bootstrap / Setup** | Ejecuta `aos init` una única vez por repositorio. | Sin intervención previa. |
| **Context Definition** | Especifica notas técnicas en `CLAUDE.md` y agregados en `.aos/**/*.local.md`. | Lee las directivas inyectadas en su managed block. |
| **Session-Start** | Plantea el objetivo o user request en lenguaje natural. | **Ejecuta `aos refresh`**: analiza gotchas previos, codebase-memory graph y plan activo. |
| **Planning & Design** | Revisa y aprueba el plan propuesto. | **Ejecuta `aos plan new`**: formaliza fases atómicas y redacta contratos en `.aos/contracts/`. |
| **Implementation** | Supervisa el diff y resuelve bloqueos de diseño. | Codifica en unidades atómicas acopladas al contrato y la memoria del grafo. |
| **Verification** | Inspecciona los reportes de auditoría y tests. | **Ejecuta `aos verify` y `aos scan --dry-run`**: corre linters, unit tests, Semgrep y Checkov. |
| **Task Closure** | Aprueba el commit final y realiza merge / push. | Marca la fase `[x]` en el plan, documenta nuevos gotchas y ejecuta `aos sync`. |

Las especificaciones detalladas de cada fase viven en `.aos/hooks/` (`session-start.md`, `pre-task.md`, `post-task.md`).

---

## 4. Instalación y Quickstart

```bash
pip install git+https://github.com/tu-usuario/dass-aos.git
# o, para desarrollar el motor:
git clone https://github.com/tu-usuario/dass-aos.git && pip install -e dass-aos
```

Esto registra el ejecutable `aos`. Si no está en el PATH, `python -m dass_aos <comando>` es equivalente.

### Dependencias externas

El núcleo no tiene dependencias. Las herramientas externas son opcionales; `aos refresh` avisa de las que faltan **solo si aplican al proyecto**.

| Herramienta | Para qué | Cuándo aplica | Instalación |
|---|---|---|---|
| Semgrep | SAST (`aos scan`) | Siempre | `pip install "dass-aos[scan]"` o `pip install semgrep`. En Windows nativo está en beta: usa `PYTHONUTF8=1`; si falla, WSL o Docker. |
| Checkov | IaC, contenedores y pipelines (`aos scan`) | Solo si hay IaC (Terraform, Bicep, Dockerfile, Helm, Kustomize, Serverless, CDK, CI pipelines… ver `applies_when` en `checkov-scan.md`) | `pip install "dass-aos[scan]"` o `pip install checkov` |
| codebase-memory | Grafo estructural del código (MCP) | Siempre | Binario `codebase-memory-mcp` en el PATH (ver su repositorio). Indexa cada proyecto en la base de datos del usuario, no en `.aos/`: la primera vez, `index_repository` con la ruta del proyecto |
| context7 | Documentación actualizada de librerías (MCP); obligatorio para `adapt-native` | Siempre | Servidor remoto `https://mcp.context7.com/mcp`, sin instalación. API key opcional (más rate limit) en context7.com |
| playwright-cli | Vía web de `live-verify`: el agente abre la app en un navegador sin interfaz, la recorre, captura y lee la consola | Solo si hay frontend web (`package.json` o `*.html` a uno o dos niveles) | `npm install -g @playwright/cli@latest` y una vez `playwright-cli install --skills -g` (skill global de Claude Code). Otras herramientas leen la `SKILL.md` que indica `playwright-cli --help` |

Los servidores MCP se declaran una sola vez, de forma neutral, en `.aos/mcp-config.json`; `adapt-native` los traduce al formato de tu herramienta.

Desde la raíz del proyecto a gestionar, indicando las herramientas de IA que usas:
```bash
aos init antigravity                  # una
aos init claude-code antigravity      # varias; más adelante, `aos init <otra>` la añade
```
Herramientas: `claude-code`, `antigravity`, `gemini-cli`, `codex`, `opencode`, `cursor`, `windsurf`. Sin argumento, `aos init` usa las ya configuradas o las que detecta en el repo: carpetas propias (`.claude/`, `.cursor/`, `.agents/hooks.json`…) o archivos de instrucciones que no haya escrito DASS-AOS. `.agents/skills/` no cuenta, porque es el estándar compartido de skills. Si no encuentra ninguna, no escribe nada y te pide que la indiques.

**Proyectos anteriores a 0.6.0** (tienen los cinco archivos de instrucciones): ejecuta `aos init <tus herramientas>` una vez para declararlas. Los archivos de las demás no se borran; si no los usas, bórralos tú y ya no se recrearán.

Este comando genera:
- `.aos/`: estado local del proyecto (contratos, planes, gotchas, ADRs, roles, skills y configuración).
- `.aos/config.json` con los comandos de lint/test **detectados según el stack** (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`). Edítalo si la detección no acierta.
- **Solo el archivo de instrucciones de cada herramienta elegida**, gobernado por DASS-AOS y preservando la sección `## Notas personalizadas del proyecto`: `claude-code` → `CLAUDE.md`; `antigravity` y `gemini-cli` → `GEMINI.md`; `codex` y `opencode` → `AGENTS.md`; `cursor` → `.cursorrules`; `windsurf` → `.windsurfrules`. La elección queda en `.aos/config.json` (`"tools"`), y `aos sync` crea solo esos archivos (los que ya existan de otras herramientas se siguen actualizando, no se borran).
- Para `claude-code` y `antigravity`, sus nativos (subagentes y skills) vía `aos adapt-native`. El hook de inicio de sesión queda **pendiente** hasta que lo revises y ejecutes `aos adapt-native <herramienta> --yes`.
- `.git/hooks/pre-commit` (si hay repo git y no existe ya un hook): ejecuta `aos verify`. Nunca bloquea si DASS-AOS o Python no están instalados. Si ya tenías un hook (p. ej. de 0.4.0), `aos init` no lo pisa: reemplázalo a mano por el que delega en `.aos/hooks/pre_commit.py`.

---

## 5. Adaptar DASS-AOS al Proyecto

Los roles y skills del motor son genéricos a propósito. Cada proyecto los adapta sin editarlos ([ADR-003](.aos/decisions/ADR-003-base-motor-agregados-locales.md)):

| Quiero… | Hago… |
|---|---|
| Añadir reglas propias a un rol del motor | Crear `.aos/agents/<rol>.local.md`. `aos sync` lo anexa al rol como "Agregados del proyecto". |
| Ajustar una skill del motor | Crear `.aos/skills/specs/<skill>.local.md`. |
| Un rol o skill exclusivo del proyecto | Crear `.aos/agents/<nuevo>.md` o `.aos/skills/specs/<nueva>.md`. El motor no lo toca. |
| Recibir mejoras del motor | `pip install -U dass-aos && aos sync`. Los roles/skills base se regeneran; los `.local.md` se conservan. |
| Cambiar comandos de verificación | Editar `lint_command` / `test_command` / `migration_command` en `.aos/config.json`. |

- Los `.aos/agents/*.md` y `.aos/skills/specs/*.md` del motor llevan el marcador `<!-- DASS-AOS-GENERATED`: **no los edites**. Si `sync` encuentra uno editado a mano, no lo sobreescribe y te indica que muevas los cambios al `.local.md`.
- Una skill puede declarar `applies_when: ["glob", ...]` en su frontmatter: solo se lista en las instrucciones si algún glob encuentra archivos en el proyecto (p. ej. `db-migration-check` solo aparece si hay `migrations/`, `alembic.ini`, `prisma/schema.prisma`…).
- Toda skill declara `cost:` (`on-demand`, `always-on`, `enforced` o `delegated`). **La prosa siempre activa es el bloque gestionado** de `CLAUDE.md`/`AGENTS.md`, y es lo caro: si crece, `aos doctor` avisa y propone mover detalle a una skill.

## 5.0 Requisitos: PRD → TRD → contratos → plan

El *qué* y el *por qué* no viven ya en el mensaje original ni se reconstruyen leyendo el diff ([ADR-007](.aos/decisions/ADR-007-capa-de-requisitos-y-grafo-de-codigo.md)). Viven en `.aos/specs/`:

| Documento | Responde a | Lo revisa |
|---|---|---|
| `NNN-<slug>.prd.md` | **PRD** — qué problema, para quién, y **cómo sabemos que funcionó** (criterios de aceptación medibles) | negocio / producto |
| `NNN-<slug>.trd.md` | **TRD** — cómo se construye y por qué así; contratos afectados, datos, riesgos, plan de prueba y observabilidad | ingeniería |

```bash
aos spec new prd --title "Export de facturas"   # → .aos/specs/001-export-de-facturas.prd.md
aos spec new trd --title "Export de facturas"   # → .aos/specs/001-export-de-facturas.trd.md (mismo NNN)
```

- El PRD y el TRD **comparten el número** con el `.design.md` de la misma funcionalidad.
- **La spec se cita, nunca se parafrasea**: los handoffs a subagentes y el `.design.md` apuntan a la ruta y a la sección. Reformular el requisito con otras palabras es un defecto.
- **Vía corta:** un cambio pequeño y comprendido no necesita PRD. Sin criterios de aceptación medibles, no se pasa al TRD.
- El PRD y el TRD **sobreviven al plan**: cuando el plan se archiva, la spec se queda.

## 5.1 Flujo de entrega por riesgo: requisitos, fases, verificación en vivo y revisión con recibo

Cuatro skills del motor ([ADR-006](.aos/decisions/ADR-006-flujo-de-entrega-del-motor.md), [ADR-008](.aos/decisions/ADR-008-enrutado-por-riesgo-y-revision-con-recibo.md)), sacadas de proyectos reales:

| Skill | Cuándo | Qué hace |
|---|---|---|
| `spec-driven` | Funcionalidad con alcance de producto | PRD con criterios medibles → TRD que cita el PRD → contratos → plan que enlaza ambos. Vía corta si el cambio es pequeño |
| `phased-delivery` | Cambios con **riesgo nombrado** (datos, seguridad, contratos compartidos, concurrencia, entrega) o poco comprendidos | Línea base → exploración → requisitos y decisiones → plan con un `Gate:` por fase → implementación en orden de dependencias → `live-verify` → revisión con recibo → cierre documentado |
| `live-verify` | Al cerrar una fase que toca UI, API, CLI o escritorio | Quien implementa levanta la app en un entorno desechable, la ejercita (navegador con `playwright-cli`, `curl`, el comando real o scripts de escritorio), mira la evidencia y se corrige, hasta 3 rondas |
| `adversarial-review` | Cambios con riesgo nombrado, antes de dar una fase por cerrada | Congela el candidato (hash) → tier por riesgo (0 lentes / 1 lente / 4R) → un revisor por lente → un `adversarial-verifier` intenta refutar cada hallazgo (en caso de duda, falso) → **una sola corrección acotada** → acuse |

**El tamaño se decide por riesgo y comprensión, nunca por número de archivos.** Un bug de tres líneas en una migración es grande; un renombrado en veinte archivos de texto es pequeño. Y sin un **motivo de delegación** que se pueda nombrar (exploración, escritores en paralelo, backstop de contexto, verificador independiente), el agente trabaja inline, sin subagentes.

Lo propio de cada proyecto va en el `.local.md` de cada skill: lentes y qué buscar, gates con comandos exactos, cómo levantar la app y los anchos de pantalla. **El entorno desechable se declara solo en `live-verify.local.md`.** La evidencia web queda en `.playwright-cli/`, que `aos init` y `aos sync` añaden a `.gitignore`.

**Proyectos con versiones propias** (p. ej. una `adversarial-review.md` hecha a mano): `aos sync` las omite con "OMITIDO: editado a mano". Mueve lo propio del proyecto a `<skill>.local.md`, borra el archivo y vuelve a ejecutar `aos sync`. Los hooks (`.aos/hooks/*.md`) y las plantillas de plan son del proyecto y `sync` no los toca: para recibir la versión nueva, bórralos y ejecuta `aos init`.

**Proyectos anteriores a 0.7.0:** para recibir la capa de requisitos y el flujo por riesgo, borra `.aos/hooks/*.md`, `.aos/plans/templates/*.md` y ejecuta `aos init`, después `aos sync` (`spec-driven` y las skills reescritas llegan solas por `sync`; `.aos/specs/` y `.aos/knowledge/lessons/` se crean al inicializar). `.aos/config.json` gana `deny_paths`: si falta, `aos doctor` avisa y el pre-commit no bloquea secretos.

## 5.2 Integración nativa con tu herramienta (`aos adapt-native`)

`.aos/` es la fuente única. Cada herramienta de IA necesita sus propios formatos (subagentes, skills, hooks), que se generan desde `.aos/` y **no se commitean**: cada dev los genera en su máquina.

**Claude Code y Antigravity: generador determinista** ([ADR-005](.aos/decisions/ADR-005-generador-nativo-por-herramienta.md)):
```bash
aos adapt-native claude-code --yes      # o: antigravity. --dry-run muestra los cambios sin escribir
```
- Sin `--yes` escribe subagentes y skills, pero **no** hooks ni permisos: los muestra como PENDIENTE para que los revises.
- Es idempotente: una segunda ejecución dice "al día, sin cambios". Nunca toca un archivo sin el marcador `DASS-AOS-GENERATED`, fusiona JSON conservando lo ajeno y borra solo lo que generó y ya no aplica.
- No crea servidores MCP: reutiliza los que tengas a nivel de usuario (`codebase-memory`, `context7`) y avisa si falta alguno.

| | Claude Code | Antigravity 2.0 |
|---|---|---|
| Roles | `.claude/agents/<rol>.md`; `tools_allowed` → `disallowedTools` (**nativo**). Prefijos de shell y subconjunto de MCP: convención | Sin subagentes en archivo: el bloque gestionado de `GEMINI.md` indica delegar con `define_subagent` y qué roles van sin escritura (**convención**) |
| Skills | `.claude/skills/<x>/SKILL.md` | `.agents/skills/<x>/SKILL.md` |
| Inicio de sesión | Hook `SessionStart` en `.claude/settings.local.json` (**nativo**) | Hook `PreInvocation` en `.agents/hooks.json`, que inyecta `aos refresh` una vez por conversación (**emulado**) |
| MCP | Usuario (`~/.claude.json`) o plugin | Global (`~/.gemini/config/mcp_config.json`) |

**Otras herramientas** (Codex, Cursor, OpenCode, Gemini CLI…): el bloque gestionado le ordena a su agente ejecutar la skill `adapt-native` ([ADR-004](.aos/decisions/ADR-004-adaptacion-nativa-delegada.md)), que consulta el formato vigente con context7 o la web, genera lo equivalente y registra lo hecho. Traduce `tools_allowed` del vocabulario neutral (`read`, `search`, `edit`, `write`, `shell`, `shell:<prefijo>`, `web`, `mcp:<servidor>`); `aos sync` falla si un rol usa un valor fuera del vocabulario.

**Manifiesto y desincronización:** lo hecho queda en `.aos/native/<herramienta>.json` (ignorado en git), con `enforcement` (qué es nativo y qué convención) y `source_hash`. Si cambias roles, skills, hooks o MCP en `.aos/`, `aos refresh` y `aos sync` marcan **DESACTUALIZADO** e indican el comando que hay que volver a ejecutar.

## 5.3 Auditoría del harness (`aos doctor` y `aos status`)

```bash
aos doctor            # solo diagnóstico: no escribe nada y no bloquea commits
aos doctor --strict   # sale con 1 si hay hallazgos de nivel error
aos status            # Working | Checking | Ready | Needs decision
aos status --json     # lo mismo, para scripts y hooks
```

`aos doctor` responde a una sola pregunta: **¿lo que el agente carga coincide con lo que `.aos/` declara?** Comprueba el frontmatter de skills y roles (`name` que coincide con el archivo, `description`, `cost`), skills que no se listan, `.local.md` huérfanos, el tamaño del bloque siempre activo (~tokens), `tools_allowed` contra el vocabulario de ADR-004, nativos desactualizados, PRD sin TRD, `deny_paths` ausente y dependencias externas. **Ningún hook lo ejecuta**: es diagnóstico.

`aos status` deriva el estado de los archivos, no del criterio de un modelo: pregunta registrada sin respuesta o siguiente fase de requisitos → `Needs decision`; siguiente fase de implementación → `Working`; de verificación → `Checking`; sin fases pendientes (o sin plan activo) → `Ready`.

---

## 6. Estructura

```
dass-aos/ (motor)
├── pyproject.toml
├── aos.py                     Atajo para ejecutar el CLI desde el código fuente
├── dass_aos/
│   ├── cli.py                 Entrada del CLI (`aos` / `python -m dass_aos`)
│   ├── bootstrap.py           aos init
│   ├── sync.py                aos sync (instrucciones + roles/skills del motor)
│   ├── memory.py              aos refresh
│   ├── scanners.py            aos scan (Semgrep / Checkov)
│   ├── verifier.py            aos verify (lint / test / migración, detección de stack)
│   ├── generator.py           aos generate-client
│   ├── plans.py               aos plan new
│   ├── specs.py               aos spec new (PRD/TRD)
│   ├── doctor.py              aos doctor (auditoría del harness, solo lectura)
│   ├── status.py              aos status (estado derivado de archivos)
│   ├── backup.py              snapshot antes de reescribir un archivo
│   └── templates/             Todo lo que `aos init` copia a .aos/ (misma estructura)
├── docs/
│   ├── ARCHITECTURE.md
│   └── CODE-GRAPH-OPTIONS.md  codebase-memory vs CodeGraph (decisión y cuándo revisarla)
└── tests/
```

```
mi-proyecto/
├── .aos/
│   ├── config.json            Comandos de verificación + deny_paths del pre-commit
│   ├── mcp-config.json        Servidores MCP neutrales (codebase-memory, context7)
│   ├── native/                Manifiestos de adapt-native (por dev, fuera de git)
│   ├── .backups/              Snapshots de lo que el motor reescribió (fuera de git)
│   ├── agents/                Roles (generados + *.local.md del proyecto)
│   ├── skills/specs/          Skills (generadas + *.local.md del proyecto)
│   ├── skills/bin/            Utilidades standalone (smoke test, commit atómico)
│   ├── hooks/                 Especificaciones de lifecycle + pre_commit.py
│   ├── contracts/             OpenAPI 3.x y CloudEvents schemas
│   ├── specs/                 PRD y TRD (NNN-<slug>.prd.md / .trd.md)
│   ├── plans/{active,archive,templates}/
│   ├── knowledge/gotchas/     Trampas y aprendizajes no obvios
│   ├── knowledge/lessons/     LEDGER.md: lecciones con evidencia
│   ├── decisions/             ADRs del proyecto
│   ├── ci/                    Pipelines de seguridad listos para copiar
├── CLAUDE.md, AGENTS.md, GEMINI.md, .cursorrules, .windsurfrules
```

---

## 7. Referencia de Comandos CLI

| Comando | Función Técnica | Ejecutado por |
|---|---|---|
| `aos init [<herramienta>...] [--project-root <ruta>]` | Inicializa `.aos/` para las herramientas indicadas (o detectadas): su archivo de instrucciones y, si tienen generador, sus nativos. Repetirlo con otra herramienta la añade. | Desarrollador |
| `aos refresh [--gotchas-limit <N>]` | Extrae gotchas recientes, codebase-memory graph status y active task. | Agente (Session-Start) |
| `aos plan new <tipo> --title <título>` | Genera un plan activo a partir de template (`feature`, `bugfix`, `refactor`, `security`). | Agente (Pre-Task) |
| `aos spec new prd\|trd --title <título>` | Crea `.aos/specs/NNN-<slug>.{prd,trd}.md`; el TRD reutiliza el número del PRD con el mismo título. | Agente (Pre-Task) |
| `aos status [--json]` | Estado derivado de archivos: `Working`, `Checking`, `Ready` o `Needs decision`. | Agente / Desarrollador |
| `aos doctor [--strict]` | Audita el harness cargado contra lo que declara `.aos/`. Solo lectura; ningún hook lo ejecuta. | Agente / Desarrollador |
| `aos verify [--type lint\|test\|migration] [--strict]` | Ejecuta linters, test suites y migrations (configurados o autodetectados). Omite herramientas no instaladas salvo con `--strict`. | Agente (Post-Task) |
| `aos scan [--tool semgrep\|checkov] [--dry-run]` | Ejecuta SAST (Semgrep) e IaC (Checkov, solo si hay IaC o con `--tool checkov`) con modo dry-run local. | Agente (Post-Task) |
| `aos adapt-native <herramienta> [--dry-run] [--yes]` | Genera los nativos de `claude-code` o `antigravity` desde `.aos/` (hooks y permisos solo con `--yes`). | Desarrollador / Agente |
| `aos refresh --hook antigravity` | Lo invoca el hook de Antigravity: lee su JSON por stdin e inyecta el refresco una vez por conversación. | Antigravity |
| `aos native-hash` | Imprime el hash de las fuentes que `adapt-native` registra en su manifiesto. | Agente (skill `adapt-native`) |
| `aos sync [--project-root <ruta>]` | Regenera managed blocks y roles/skills del motor respetando notas humanas y `.local.md`. | Agente (Post-Task) |
| `aos generate-client --contract <ruta>` | Genera typed client stubs desde contratos OpenAPI. | Agente / Desarrollador |

---

## 8. Roles Especializados de Agentes

Ubicados en `.aos/agents/`, definen tools permitidas, constraints y output protocols:

- **App Builder** (`app-builder.md`): Diseño end-to-end e implementación por fases guiada por contratos.
- **Architect** (`architect.md`): Redacción de ADRs, definición de contratos y system boundaries.
- **Reviewer** (`reviewer.md`): Code & security review estructurado en formato `file:line`.
- **Refactorer** (`refactorer.md`): Mejoras estructurales garantizando comportamiento observable idéntico.
- **Security Auditor** (`security-auditor.md`): Auditoría de autenticación, gestión de secrets, IaC y dependencias.
- **QA Tester** (`qa-tester.md`): Generación de test suites, regression tests y contract smoke tests; evidencia en vivo con `live-verify`.
- **Adversarial Verifier** (`adversarial-verifier.md`): Intenta refutar cada hallazgo de revisión contra el código real antes de corregirlo; no edita.

---

## 9. Verificación y Auditoría en CI/CD

`aos init` copia pipelines listos para producción a `.aos/ci/`:
- **GitHub Actions**: `.aos/ci/github-actions/security.yml` → copiar a `.github/workflows/`
- **GitLab CI**: `.aos/ci/gitlab/security.yml`

Ambos ejecutan Semgrep y Checkov en containers en modo estricto, asegurando paridad entre las comprobaciones locales del agente y las del pipeline.

---

## 10. Desarrollo del Motor

Arquitectura interna y decisiones de diseño: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

```bash
python -m unittest discover -s tests -p "test_*.py" -v
ruff check .
```

---

## 11. Licencia

Distribuido bajo licencia MIT. Consulte el archivo `LICENSE` para más detalles.
