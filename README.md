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

Desde la raíz del proyecto a gestionar:
```bash
aos init
```

Este comando genera:
- `.aos/`: estado local del proyecto (contratos, planes, gotchas, ADRs, roles, skills y configuración).
- `.aos/config.json` con los comandos de lint/test **detectados según el stack** (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`). Edítalo si la detección no acierta.
- `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules`, `.windsurfrules`: instrucciones gobernadas por DASS-AOS, preservando la sección `## Notas personalizadas del proyecto`.
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
│   └── templates/             Todo lo que `aos init` copia a .aos/ (misma estructura)
├── docs/ARCHITECTURE.md
└── tests/
```

```
mi-proyecto/
├── .aos/
│   ├── config.json            Comandos de verificación
│   ├── mcp-config.json        Servidores MCP (codebase-memory)
│   ├── agents/                Roles (generados + *.local.md del proyecto)
│   ├── skills/specs/          Skills (generadas + *.local.md del proyecto)
│   ├── skills/bin/            Utilidades standalone (smoke test, commit atómico)
│   ├── hooks/                 Especificaciones de lifecycle + pre_commit.py
│   ├── contracts/             OpenAPI 3.x y CloudEvents schemas
│   ├── plans/{active,archive,templates}/
│   ├── knowledge/gotchas/     Trampas y aprendizajes no obvios
│   ├── decisions/             ADRs del proyecto
│   ├── ci/                    Pipelines de seguridad listos para copiar
│   └── memory/                Base de datos de codebase-memory
├── CLAUDE.md, AGENTS.md, GEMINI.md, .cursorrules, .windsurfrules
```

---

## 7. Referencia de Comandos CLI

| Comando | Función Técnica | Ejecutado por |
|---|---|---|
| `aos init [--project-root <ruta>]` | Inicializa `.aos/` y sincroniza agent instruction files. | Desarrollador |
| `aos refresh [--gotchas-limit <N>]` | Extrae gotchas recientes, codebase-memory graph status y active task. | Agente (Session-Start) |
| `aos plan new <tipo> --title <título>` | Genera un plan activo a partir de template (`feature`, `bugfix`, `refactor`, `security`). | Agente (Pre-Task) |
| `aos verify [--type lint\|test\|migration] [--strict]` | Ejecuta linters, test suites y migrations (configurados o autodetectados). Omite herramientas no instaladas salvo con `--strict`. | Agente (Post-Task) |
| `aos scan [--tool semgrep\|checkov] [--dry-run]` | Ejecuta SAST (Semgrep) e IaC (Checkov) con modo dry-run local. | Agente (Post-Task) |
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
- **QA Tester** (`qa-tester.md`): Generación de test suites, regression tests y contract smoke tests.

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
