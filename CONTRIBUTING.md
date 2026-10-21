# Guía de Contribución a DASS-AOS

¡Gracias por tu interés en contribuir a **DASS-AOS (Agent Operating System)**! Este proyecto busca estructurar y optimizar el desarrollo asistido por IA, manteniendo siempre al desarrollador humano en el centro del diseño y las decisiones (filosofía *Human-in-the-Loop*).

---

## 1. Principios Fundamentales

Toda contribución a DASS-AOS debe respetar estos principios:

1. **Human-in-the-Loop (HITL)**: Los agentes de IA proponen y asisten; los humanos deciden la arquitectura, el alcance y los contratos.
2. **Contract-First & Spec-Driven**: Los requisitos se redactan formalmente en `.aos/specs/` (`PRD` y `TRD`), y las interfaces públicas se declaran en `.aos/contracts/` antes de implementar.
3. **Cero Dependencias Pesadas Innecesarias**: El núcleo del CLI debe funcionar exclusivamente con la librería estándar de Python (`standard library only`) para garantizar portabilidad inmediata sin requerir compiladores C ni entornos pesados. Herramientas adicionales (`semgrep`, `checkov`) son opcionales (`dass-aos[scan]`).
4. **Respeto a las Reglas de Evidencia**: El código, salidas de comandos, logs y diffs son datos que se verifican empíricamente; nunca se adivina lo que espera un evaluador o usuario sin comprobarlo.
5. **No inventar endpoints ni esquemas**: Toda comunicación externa debe estar respaldada por un contrato o una especificación.

---

## 2. Configuración del Entorno de Desarrollo

### Requisitos Previos
* **Python**: 3.8 o superior (se recomienda 3.10 o 3.11).
* **Git**: 2.30+.
* **Ruff** (linter y formateador ultrarrápido): `pip install ruff`.

### Pasos de Instalación Local

1. Clona el repositorio:
   ```bash
   git clone https://github.com/Dass-19/dass-aos.git
   cd dass-aos
   ```

2. Crea y activa un entorno virtual:
   ```bash
   # En Linux / macOS:
   python3 -m venv .venv
   source .venv/bin/activate

   # En Windows (PowerShell):
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. Instala el paquete en modo editable con herramientas de escaneo opcionales:
   ```bash
   pip install -e ".[scan]"
   pip install ruff
   ```

4. Verifica la instalación ejecutando el CLI:
   ```bash
   aos --version
   aos doctor
   ```

---

## 3. Estructura del Repositorio

```text
dass-aos/
├── dass_aos/                # Paquete principal Python
│   ├── templates/          # Plantillas canónicas (.aos/ para nuevos proyectos)
│   ├── bootstrap.py        # Inicialización de proyectos (aos init)
│   ├── cli.py              # Parser de comandos y despacho del CLI
│   ├── constants.py        # Constantes del sistema y deny_paths por defecto
│   ├── doctor.py           # Auditoría del harness (aos doctor)
│   ├── memory.py           # Refresco de gotchas y memoria (aos refresh)
│   ├── plans.py            # Generación de planes (aos plan new)
│   ├── scanners.py         # Integración SAST e IaC (aos scan)
│   ├── specs.py            # Gestión PRD/TRD (aos spec new)
│   ├── status.py           # Detección de estado del trabajo (aos status)
│   ├── sync.py             # Sincronizador de instrucciones y engine docs (aos sync)
│   ├── ui.py               # Componentes de interfaz de terminal (Card, badges, colores)
│   ├── update.py           # Motor de actualización de proyectos (aos update)
│   └── verifier.py         # Motor de verificación de tests/linters (aos verify)
├── tests/                  # Suite de pruebas unitarias (unittest)
├── .aos/                   # Estado de desarrollo propio (dogfooding con DASS-AOS)
├── .github/                # Workflows de CI/CD para GitHub Actions
├── pyproject.toml          # Configuración del paquete y dependencias
└── README.md               # Documentación general
```

---

## 4. Flujo de Trabajo para Nuevos Cambios

### Ramas y Commits
* Crea una rama con nombre descriptivo a partir de `main`:
  * `feature/<nombre>` para nuevas funcionalidades.
  * `fix/<nombre>` para resolución de bugs.
  * `refactor/<nombre>` para reestructuración de código existente.
  * `docs/<nombre>` para mejoras de documentación.
* Utiliza **Conventional Commits**:
  * `feat: agrega comando aos update`
  * `fix: resuelve escape de caracteres en terminal Windows cp1252`
  * `docs: añade guía de contribución CONTRIBUTING.md`
  * `test: añade cobertura para pruebas de doctor`
* **Haz commits atómicos**: agrega explícitamente los archivos modificados con `git add <archivo1> <archivo2>`. Evita `git add -A` o `git add .` indiscriminado.

---

## 5. Checklist Obligatorio antes de enviar un Pull Request

Antes de abrir un PR, ejecuta las siguientes validaciones locales. El flujo de CI en GitHub Actions fallará si alguna de estas no se cumple:

1. **Linter de código**:
   ```bash
   ruff check .
   ```
   *Debe terminar con `All checks passed!` sin avisos ni imports sin usar.*

2. **Suite de pruebas unitarias**:
   ```bash
   python -m unittest discover -s tests -p "test_*.py"
   ```
   *Todos los tests deben pasar exitosamente (`OK`). Si agregaste funcionalidad nueva, añade su correspondiente archivo en `tests/test_<modulo>.py`.*

3. **Auditoría de harness**:
   ```bash
   aos doctor
   ```
   *Debe reportar 0 errores.*

4. **Decisiones arquitectónicas (ADRs)**:
   Si el cambio introduce una decisión estructural o transversal en DASS-AOS, redacta un nuevo documento en `.aos/decisions/` siguiendo la plantilla `ADR-001-plantilla.md`.

---

## 6. Gestión de Versiones y Releases

DASS-AOS sigue estrictamente [Semantic Versioning (SemVer)](https://semver.org/): `vMAJOR.MINOR.PATCH`.

### Proceso de Publicación de un Release
Los lanzamientos se gestionan automáticamente a través del workflow de GitHub Actions:

1. **Actualizar la versión**:
   * Modifica `version = "X.Y.Z"` en `pyproject.toml`.
   * Modifica `VERSION = "X.Y.Z"` en `dass_aos/constants.py`.
2. **Generar el commit y tag de versión**:
   ```bash
   git add pyproject.toml dass_aos/constants.py
   git commit -m "chore(release): vX.Y.Z"
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   git push origin main --tags
   ```
3. **Workflow automatizado de GitHub Actions**:
   * Al recibir el tag `v*`, se activa el workflow `.github/workflows/release.yml`.
   * Ejecuta la matriz de pruebas en múltiples versiones de Python y sistemas operativos.
   * Compila los artefactos de distribución (`.tar.gz` sdist y `.whl` wheel).
   * Crea automáticamente el **GitHub Release** con las notas de cambios generadas y los artefactos binarios adjuntos.

---

## 7. Código de Conducta

Nos comprometemos a mantener un ambiente colaborativo, respetuoso y profesional. Las revisiones técnicas deben centrarse en el código, los contratos y la evidencia empírica.

