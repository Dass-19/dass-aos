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

El framework opera bajo una separación estricta entre la gobernanza humana y la ejecución técnica del agente:

| Fase del Workflow | Rol del Desarrollador (Humano) | Rol del AI Agent |
|---|---|---|
| **Bootstrap / Setup** | Ejecuta `aos init` una única vez por repositorio. | Sin intervención previa. |
| **Context Definition** | Especifica notas técnicas o restricciones en `CLAUDE.md`. | Lee las directivas inyectadas en su managed block. |
| **Session-Start** | Plantea el objetivo o user request en lenguaje natural. | **Ejecuta `aos refresh`**: analiza gotchas previos, codebase-memory graph y plan activo. |
| **Planning & Design** | Revisa y aprueba el plan propuesto. | **Ejecuta `aos plan new`**: formaliza fases atómicas y redacta contratos en `.aos/contracts/`. |
| **Implementation** | Supervisa el diff y resuelve bloqueos de diseño. | Codifica en unidades atómicas acopladas al contrato y la memoria del grafo. |
| **Verification** | Inspecciona los reportes de auditoría y tests. | **Ejecuta `aos verify` y `aos scan --dry-run`**: corre linters, unit tests, Semgrep y Checkov. |
| **Task Closure** | Aprueba el commit final y realiza merge / push. | Marca la fase `[x]` en el plan, documenta nuevos gotchas y ejecuta `aos sync`. |

---

## 4. Instalación y Quickstart

### Instalación en el entorno
```bash
git clone https://github.com/tu-usuario/dass-aos.git
cd dass-aos
pip install -e .
```

### Inicialización en un repositorio existente
Navegue a la raíz del proyecto a gestionar:
```bash
aos init
```
*(O directamente vía script sin instalación previa: `python /ruta/a/dass-aos/aos.py init`)*

Este comando genera:
- `.aos/`: Directorio de estado local aislado (contracts, active/archive plans, gotchas, ADRs y configuración).
- `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules`: Archivos de instrucciones gobernados por DASS-AOS, preservando la sección `## Notas personalizadas del proyecto`.

---

## 5. Arquitectura del Repositorio y Estado Local

```
DASS-AOS (Engine & CLI)
├── aos.py                     Punto de entrada ejecutable
├── pyproject.toml             Configuración de paquete pip / PyPI
├── dass_aos/                  Módulos centrales en Python 3 puro
│   ├── bootstrap.py           Inicialización de repositorios
│   ├── sync.py                Sincronización idempotente de instrucciones
│   ├── memory.py              Refresco de memoria de inicio de sesión
│   ├── scanners.py            Integración con Semgrep (SAST) y Checkov (IaC)
│   ├── verifier.py            Ejecución agnóstica de linters y test suites
│   ├── generator.py           Generación de clientes tipados desde OpenAPI
│   └── plans.py               Gestión de plantillas de planes
├── agents/                    Definiciones de roles base
├── contracts/                 Plantillas de interfaces (HTTP, events, schemas)
├── decisions/                 Plantillas de Architecture Decision Records (ADRs)
├── plans/templates/           Plantillas de planes (feature, bugfix, refactor, security)
└── hooks/                     Especificaciones de lifecycle hooks
```

En el repositorio del proyecto:
```
target-project/
├── .aos/
│   ├── config.json            Configuración de comandos de verificación
│   ├── mcp-config.json         Configuración de servidores MCP locales
│   ├── contracts/              Contratos OpenAPI 3.x y CloudEvents schemas
│   ├── plans/active/           Planes de tareas activos por fases
│   ├── plans/archive/          Historial de planes completados
│   ├── knowledge/gotchas/      Knowledge base de fallos resueltos y trampas
│   ├── decisions/              ADRs del proyecto
│   └── memory/                 Base de datos SQLite para codebase-memory
├── CLAUDE.md                   Instrucciones sincronizadas para Claude Code
├── AGENTS.md                   Instrucciones estándar para agentes
├── GEMINI.md                   Instrucciones para Gemini / Antigravity
└── .cursorrules                Directivas para Cursor / Windsurf
```

---

## 6. Referencia de Comandos CLI

| Comando | Función Técnica | Ejecutado por |
|---|---|---|
| `aos init [--project-root <ruta>]` | Inicializa `.aos/` y sincroniza agent instruction files. | Desarrollador |
| `aos refresh [--gotchas-limit <N>]` | Extrae gotchas recientes, codebase-memory graph status y active task. | Agente (Session-Start) |
| `aos plan new <tipo> --title <título>` | Genera un plan activo a partir de template (`feature`, `bugfix`, `refactor`, `security`). | Agente (Pre-Task) |
| `aos verify [--type lint\|test\|migration]` | Ejecuta linters, test suites y migrations (autodetectados o configurados). | Agente (Post-Task) |
| `aos scan [--tool semgrep\|checkov] [--dry-run]` | Ejecuta SAST (Semgrep) e IaC (Checkov) con modo dry-run local. | Agente (Post-Task) |
| `aos sync [--project-root <ruta>]` | Regenera managed blocks respetando human notes. | Agente (Post-Task) |
| `aos generate-client --contract <ruta>` | Genera typed client stubs desde contratos OpenAPI. | Agente / Desarrollador |

---

## 7. Roles Especializados de Agentes

Ubicados en `agents/`, definen tools permitidas, constraints y output protocols:

- **App Builder** (`app-builder.md`): Diseño end-to-end e implementación por fases guiada por contratos.
- **Architect** (`architect.md`): Redacción de ADRs, definición de contratos y system boundaries.
- **Reviewer** (`reviewer.md`): Code & security review estructurado en formato `file:line`.
- **Refactorer** (`refactorer.md`): Mejoras estructurales garantizando comportamiento observable idéntico.
- **Security Auditor** (`security-auditor.md`): Auditoría de autenticación, gestión de secrets, IaC y dependencias.
- **QA Tester** (`qa-tester.md`): Generación de test suites, regression tests y contract smoke tests.

---

## 8. Verificación y Auditoría en CI/CD

El repositorio incluye pipelines listos para producción:
- **GitHub Actions**: `ci/github-actions/security.yml`
- **GitLab CI**: `ci/gitlab/security.yml`

Ambos ejecutan Semgrep y Checkov en containers en modo estricto, asegurando paridad completa entre las comprobaciones que el agente ejecuta localmente y las del pipeline de CI.

---

## 9. Test Suite y Desarrollo Local

El proyecto cuenta con una test suite unitaria que utiliza exclusivamente la biblioteca estándar:

```bash
# Ejecutar test suite
python -m unittest discover -s tests -p "test_*.py" -v

# Linter de código
ruff check .
```

---

## 10. Licencia

Distribuido bajo licencia MIT. Consulte el archivo `LICENSE` para más detalles.
