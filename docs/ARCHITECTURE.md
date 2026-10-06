# Arquitectura y Decisiones de Diseño de DASS-AOS

Este documento detalla la arquitectura interna, el diseño técnico y los principios fundamentales del framework DASS-AOS.

---

## 1. Filosofía Central: Motor vs. Estado Local del Proyecto

En versiones preliminares se intentaba almacenar planes, gotchas y contratos dentro del propio repositorio del framework. Esto provocaba errores de rutas y hacía imposible trabajar en múltiples proyectos a la vez.

Desde v0.4.0 se aplica una separación estricta de responsabilidades:

| Capa | Responsabilidad | Ubicación |
|---|---|---|
| **Motor** | Herramientas de CLI, roles base, plantillas, escáneres, verificación | `dass_aos/` (plantillas en `dass_aos/templates/`, empaquetadas con pip) |
| **Estado Local** | Contratos, planes activos, decisiones y gotchas del proyecto | `<raiz_proyecto>/.aos/` |
| **Directivas de Agentes** | Contexto para herramientas con bloques gestionados y notas humanas | `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules` |

```
Repositorio Destino
├── .aos/
│   ├── config.json          ← Comandos inferidos o explícitos (lint, test, migración)
│   ├── mcp-config.json       ← Servidores MCP preconfigurados (codebase-memory)
│   ├── contracts/            ← Especificaciones OpenAPI y esquemas CloudEvents
│   ├── plans/active/         ← Planes de tareas de ejecución por fases
│   ├── plans/archive/        ← Planes completados y archivados
│   ├── knowledge/gotchas/    ← Trampas no obvias descubiertas durante el desarrollo
│   ├── decisions/            ← Registros de Decisiones de Arquitectura (ADRs)
│   └── memory/               ← Base de datos SQLite / grafo para codebase-memory
├── CLAUDE.md                 ← Bloque gestionado + notas humanas
├── AGENTS.md                 ← Bloque gestionado + notas humanas
├── GEMINI.md                 ← Bloque gestionado + notas humanas
└── .cursorrules              ← Bloque gestionado + notas humanas
```

---

## 2. Ejecución Multiplataforma y Cero Dependencias Externas

DASS-AOS está programado en **Python 3 puro utilizando únicamente la biblioteca estándar**:
- Sin librerías externas obligatorias para operar el CLI.
- Sin dependencias de Bash (`.sh`) ni de PowerShell (`.ps1`).
- La función `configure_utf8_output()` garantiza que terminales de Windows con codificación heredada (como `cp1252`) no sufran fallos de `UnicodeEncodeError`.
- La resolución de rutas utiliza `pathlib.Path` en todo el código, evitando problemas con barras diagonales `/` e invertidas `\`.

---

## 3. Motor de Sincronización Idempotente

El comando `aos sync` utiliza delimitadores gestionados:
```markdown
<!-- DASS-AOS-MANAGED-START -->
... instrucciones autogeneradas, roles, skills y ciclo de vida ...
<!-- DASS-AOS-MANAGED-END -->

## Project-specific notes
(Las notas e instrucciones humanas personalizadas se conservan intactas aquí)
```
- Cuando se ejecuta `aos sync`, se buscan las marcas `<!-- DASS-AOS-MANAGED-START -->` y `<!-- DASS-AOS-MANAGED-END -->`.
- Solo se reemplaza el contenido interior de dichas marcas.
- Cualquier contenido anterior o posterior (incluida la sección `## Project-specific notes`) se preserva sin alteraciones.
- También reconoce marcas históricas (`<!-- AI-AGENT-AOS-MANAGED-START -->`) para garantizar compatibilidad retroactiva.

### Roles y skills del motor (ADR-003)
- `aos init` copia `dass_aos/templates/` a `.aos/` sin sobreescribir nada (`bootstrap.copy_missing`).
- `aos sync` regenera `.aos/agents/*.md` y `.aos/skills/specs/*.md` que tienen template en el motor (`sync.sync_engine_docs`): template + marcador `<!-- DASS-AOS-GENERATED` tras el frontmatter + contenido de `<nombre>.local.md` si existe.
- Un archivo sin marcador que difiere del template se considera editado a mano: se omite y se avisa. Roles/skills sin template en el motor son del proyecto y no se tocan.
- `applies_when: [globs]` en una skill spec filtra si se lista en las instrucciones (`sync.skill_applies`).

---

## 4. Desarrollo Guiado por Contratos (Contract-First)

Los agentes tienen estrictamente prohibido inventar endpoints, parámetros o modelos sobre la marcha.
1. Cuando una nueva funcionalidad requiere una API o un evento, el rol **Architect** o **App Builder** crea o actualiza el contrato en `.aos/contracts/http/` o `.aos/contracts/events/`.
2. `aos generate-client` genera los modelos tipados o stubs correspondientes.
3. La implementación en el código se programa contra dicho contrato.
4. `aos verify` y los tests de contrato validan que la implementación cumpla con la especificación.

---

## 5. Gates de Calidad y Seguridad

### Entorno de Desarrollo Local (Flexible)
- `aos verify`: Ejecuta linters y pruebas unitarias. `aos init` guarda en `.aos/config.json` los comandos detectados (`verifier.detect_stack_commands`: npm, Python, Cargo, Go); si siguen vacíos, se infieren en cada ejecución o se reporta `SKIPPED`. Si el ejecutable de un comando no está instalado se omite (falla solo con `--strict`), para que el pre-commit no bloquee por herramientas ausentes.
- `aos scan --dry-run`: Ejecuta Semgrep SAST y Checkov IaC. Si el desarrollador no tiene las herramientas instaladas, explica qué comando correría, cómo instalarlas y finaliza con código 0.

### Integración Continua (Estricto)
- En los pipelines de CI (`.aos/ci/github-actions/security.yml` y `.aos/ci/gitlab/security.yml`, copiados por `aos init`), Semgrep y Checkov se ejecutan en modo estricto en contenedores, bloqueando PRs ante cualquier hallazgo no mitigado.

---

## 6. Registro Histórico de ADRs
- [ADR-001: Plantilla de Architecture Decision Record](../dass_aos/templates/decisions/ADR-001-plantilla.md)
- [ADR-002: Arquitectura Híbrida CLI y Estado Local (.aos/)](../.aos/decisions/ADR-002-hibrido-cli-estado-local.md)
- [ADR-003: Base genérica del motor + agregados locales](../.aos/decisions/ADR-003-base-motor-agregados-locales.md)
