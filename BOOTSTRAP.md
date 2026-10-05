# BOOTSTRAP: Inicialización de DASS-AOS

> **Nota**: Para la guía rápida completa y documentación detallada de arquitectura, consulte [README.md](README.md) y [QUICKSTART.md](QUICKSTART.md).

---

## 1. Principio de Operación

1. El desarrollador ejecuta `aos init` una única vez en la raíz del proyecto.
2. DASS-AOS inicializa el estado local (`.aos/`) y las directivas en `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` y `.cursorrules`.
3. A partir de ese momento, el agente de IA asume la ejecución del ciclo de vida técnico:
   - `aos refresh`: al iniciar cada sesión de trabajo.
   - `aos plan new`: para planificar cambios y documentar contratos antes de codificar.
   - `aos verify` y `aos scan`: para validar linters, pruebas y seguridad antes de concluir tareas.
   - `aos sync`: para actualizar las instrucciones si cambian las reglas del proyecto.

---

## 2. Comando de Inicialización

Desde la raíz del repositorio a gestionar:

```bash
# Con el CLI instalado en el entorno:
aos init

# O ejecutando directamente desde el código fuente:
python /ruta/a/dass-aos/aos.py init
```

### Componentes creados
- `.aos/`: Directorio de estado local con contratos, planes activos/archivados, gotchas y configuración.
- `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules`: Archivos de instrucciones gobernados por DASS-AOS.
- `.aos/mcp-config.json`: Servidores MCP para `filesystem` y `codebase-memory`.
- `.aos/hooks/pre_commit.py`: Comprobaciones automáticas pre-commit.
