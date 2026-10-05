# DASS-AOS — Sistema Operativo para Agentes de IA
> Versión: 0.4.0 · 2026-10-05  
> CLI en Python 3 puro y Sistema Operativo agnóstico al stack para agentes de codificación (Claude, Cursor, Windsurf, Gemini, Antigravity, Aider)

---

## 1. Propósito

Proporcionar un sistema operativo unificado y multiplataforma para agentes de IA que trabajen en cualquier proyecto de software. DASS-AOS evita la pérdida de contexto, las alucinaciones, la rotura de contratos y la sobreescritura ciega de código mediante un ciclo de vida disciplinado, memoria viva y una única fuente de verdad.

### Garantías Principales
- **Multiplataforma**: 100% Python 3 puro (basado exclusivamente en la biblioteca estándar). Funciona de forma idéntica en Windows (PowerShell/CMD), macOS y Linux.
- **Aislamiento por Proyecto**: Cada repositorio mantiene sus propios contratos, planes activos, decisiones y gotchas dentro de un directorio local `.aos/`.
- **Sincronización Idempotente**: Genera y actualiza `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` y `.cursorrules` con bloques gestionados, preservando intactas las notas personalizadas humanas.
- **Contratos Primero (Contract-First)**: Nunca inventar endpoints ni esquemas de eventos que no estén declarados formalmente en `.aos/contracts/`.
- **Memoria Viva**: Consulta automática de trampas recientes (gotchas) y dependencias estructurales en `codebase-memory` antes de tocar código.

---

## 2. Arquitectura de Directorios

```
dass-aos/ (Motor y CLI)
├── aos.py                     ← Punto de entrada CLI raíz (python aos.py <comando>)
├── pyproject.toml             ← Configuración de empaquetado para pip install -e . / PyPI
├── dass_aos/                  ← Paquete principal de Python
│   ├── bootstrap.py           ← Lógica para 'aos init'
│   ├── sync.py                ← Lógica para 'aos sync'
│   ├── memory.py              ← Lógica para 'aos refresh'
│   ├── scanners.py            ← Lógica para 'aos scan' (Semgrep / Checkov)
│   ├── verifier.py            ← Lógica para 'aos verify' (lint / test / migración)
│   ├── generator.py           ← Lógica para 'aos generate-client'
│   └── plans.py               ← Lógica para 'aos plan new'
├── agents/                    ← Roles base especializados para agentes
├── contracts/                 ← Plantillas base de contratos (events, http, schemas)
├── decisions/                 ← Plantillas base de ADRs (ADR-001) para nuevos proyectos
├── plans/templates/           ← Plantillas de planes (feature, bugfix, refactor, security)
├── hooks/                     ← Especificaciones de ciclo de vida
└── ci/                        ← Plantillas de CI (GitHub Actions, GitLab)
```

Dentro de cualquier proyecto que adopte DASS-AOS:
```
mi-proyecto/
├── .aos/                      ← Estado local del proyecto
│   ├── contracts/             ← Especificaciones HTTP y eventos de dominio del proyecto
│   ├── plans/active/          ← Planes de tareas activos por fases
│   ├── plans/archive/         ← Planes de tareas completados y archivados
│   ├── knowledge/gotchas/     ← Trampas y aprendizajes no obvios del proyecto
│   ├── decisions/             ← ADRs específicos del proyecto
│   ├── memory/                ← Base de datos SQLite/grafo para codebase-memory
│   └── config.json            ← Configuración de lint, test y generadores del proyecto
├── CLAUDE.md                  ← Instrucciones gestionadas para Claude Code
├── AGENTS.md                  ← Instrucciones gestionadas para agentes estándar
├── GEMINI.md                  ← Instrucciones gestionadas para Gemini / Antigravity
└── .cursorrules               ← Reglas gestionadas para Cursor / Windsurf
```

---

## 3. Referencia Rápida del CLI

> **División de roles**: El desarrollador humano solo ejecuta `aos init` una vez al adoptar un proyecto. Todos los demás comandos son invocados autónomamente por el agente de IA al seguir su ciclo de vida.

| Comando | Acción | Ejecutado por |
|---|---|---|
| `python aos.py init` | Inicializa DASS-AOS en el proyecto destino (crea `.aos/` y archivos de agentes) | **Humano** |
| `python aos.py refresh` | Hook de inicio de sesión: extrae gotchas recientes, estado de memoria y tarea actual | **Agente** |
| `python aos.py plan new <tipo> --title <título>` | Instancia un nuevo plan (`feature`, `bugfix`, `refactor`, `security`) | **Agente** |
| `python aos.py verify [--type lint\|test\|migration]` | Ejecuta linters y pruebas del proyecto (autodetectados o configurados en `.aos/config.json`) | **Agente** |
| `python aos.py scan [--dry-run]` | Ejecuta los escáneres de seguridad Semgrep y Checkov (con modo simulación seguro) | **Agente** |
| `python aos.py sync` | Sincroniza `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules` | **Agente** |
| `python aos.py generate-client --contract <spec>` | Genera clientes tipados a partir de contratos OpenAPI | **Agente / Humano** |

---

## 4. Ciclo de Vida Obligatorio del Agente

1. **Inicio de Sesión (`hooks/session-start.md`)**:
   - Ejecutar `python aos.py refresh`.
   - Leer las trampas recientes y tomar nota de la tarea del plan activo.
2. **Pre-Tarea (`hooks/pre-task.md`)**:
   - Tomar **únicamente** la siguiente tarea sin marcar `[ ]` en `.aos/plans/active/`.
   - Consultar `.aos/contracts/` e inspeccionar `codebase-memory` antes de modificar archivos.
3. **En Tarea**:
   - Realizar cambios atómicos y enfocados.
4. **Post-Tarea (`hooks/post-task.md`)**:
   - Ejecutar `python aos.py verify` y `python aos.py scan`.
   - Marcar la tarea con `[x]` en el plan activo.
   - Documentar nuevos gotchas si se descubrió alguna trampa no obvia.
   - Ejecutar `python aos.py sync` si cambiaron las reglas o los contratos.
