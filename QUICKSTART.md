# Guía de Inicio Rápido de DASS-AOS

Configuración y uso del sistema en dos pasos.

---

## 1. Principio Operativo: Human-in-the-Loop

DASS-AOS está estructurado para que el desarrollador humano ejerza el rol de arquitecto y director técnico, mientras el agente de IA asume la ejecución técnica disciplinada:

1. **El desarrollador ejecuta `aos init` una única vez** para inicializar la estructura `.aos/` y generar los archivos de directivas (`CLAUDE.md`, `.cursorrules`, `GEMINI.md`, `AGENTS.md`).
2. **El agente de IA asume la ejecución del ciclo de vida técnico**: al iniciar una sesión lee estas directivas y ejecuta de forma autónoma `aos refresh`, `aos plan new`, `aos verify`, `aos scan` y `aos sync`.
3. **El desarrollador supervisa y aprueba**: define el objetivo de negocio, valida los contratos propuestos, revisa las decisiones arquitectónicas y aprueba el código final antes de integrarlo.

---

## 2. Instalación de DASS-AOS

### Opción A: Instalación editable en el entorno (Recomendado)
```bash
git clone https://github.com/tu-usuario/dass-aos.git
cd dass-aos
pip install -e .
```
Esto registra el ejecutable `aos` en el PATH de su sistema.

### Opción B: Ejecución directa sin instalación
```bash
python /ruta/a/dass-aos/aos.py --help
```

---

## 3. Inicialización en un Repositorio

Desde la raíz del proyecto que desea gestionar:
```bash
cd /ruta/a/mi-proyecto
aos init
```
*(O ejecute: `python /ruta/a/dass-aos/aos.py init`)*

### Estructura generada
1. **Directorio local `.aos/`**:
   - `contracts/`: Especificaciones OpenAPI (YAML) y esquemas de eventos (JSON).
   - `plans/active/`: Planes de tareas activos organizados por fases.
   - `knowledge/gotchas/`: Registro de trampas y lecciones aprendidas para evitar regresiones.
   - `config.json`: Comandos de verificación específicos para el stack del proyecto.
2. **Archivos de directivas de agentes**:
   - `CLAUDE.md` (Claude Code)
   - `AGENTS.md` (Agentes genéricos)
   - `GEMINI.md` (Google Antigravity / Gemini)
   - `.cursorrules` (Cursor / Windsurf)
3. **Sección de notas humanas**:
   - En cualquiera de estos archivos puede redactar notas en `## Notas personalizadas del proyecto`. DASS-AOS las preservará íntegramente en cada sincronización.

---

## 4. Flujo de Trabajo en Sesión

Una vez inicializado, el desarrollador interactúa con su agente de IA en lenguaje natural:
> *"Implementa el flujo de autenticación con tokens JWT siguiendo los contratos del proyecto."*

El agente, gobernado por sus directivas:
1. **Ejecuta `aos refresh`**: Analiza trampas previas documentadas y el estado de la memoria estructural.
2. **Ejecuta `aos plan new feature --title "jwt-auth"`**: Diseña el plan y declara o actualiza los contratos en `.aos/contracts/http/`.
3. **Implementa el código**: Trabaja en unidades atómicas contra la especificación acordada.
4. **Ejecuta `aos verify` y `aos scan --dry-run`**: Corre linters, pruebas unitarias y escaneos de seguridad antes de solicitar revisión.
5. **Cierra la tarea**: Marca la fase en el plan activo y ejecuta `aos sync`.

El desarrollador mantiene la visibilidad y el control en todo momento a través de los planes, los contratos y los reportes de verificación.
