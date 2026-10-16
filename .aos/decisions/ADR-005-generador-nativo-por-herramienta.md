---
id: 202610061900
type: decision
status: vigente
created: 2026-10-06
supersedes: "ADR-004 (puntos 1 y 2, solo para herramientas con generador)"
---

# ADR-005: Generador nativo determinista para herramientas conocidas (`aos adapt-native <tool>`)

## Contexto
ADR-004 delegó la adaptación nativa en el agente de cada herramienta (skill `adapt-native`). La primera prueba real (2026-10-06, Claude Code 2.1.274 y Antigravity 2.0) mostró que el resultado depende de cómo interprete el agente la spec:
- Antigravity escribió vocabulario neutral (`mcp:context7`, `search`) en el campo nativo `tools`, luego un pseudo-formato `mcp:server:tool`, y después nombres que no existen en su runtime (`grep_search`).
- En una re-ejecución solo actualizó el `source_hash` y se declaró "al día" sin regenerar: el hash prueba que se escribió el manifiesto, no que lo generado cumpla la spec.
- Generó subagentes en `.agents/agents/*.md` siguiendo la web, pero la versión instalada no los carga (`subagent "reviewer" not found`) y su documentación local (`~/.gemini/antigravity/builtin/skills/agy-customizations/docs/`) no los menciona.
- Claude Code, en cambio, se generó con un script determinista (`gen.py`) en una pasada, idempotente y conforme.

Formatos verificados el 2026-10-06 (corrige el contexto de ADR-004):
- **Claude Code**: `.claude/agents/*.md` (`tools` allowlist que excluye MCP no listados; sin restricción de Bash por prefijo), `.claude/skills/<x>/SKILL.md`, hook `SessionStart` en `.claude/settings.local.json`; MCP reutilizados a nivel de usuario/plugin (`mcp__<servidor>`, `mcp__plugin_<plugin>_<servidor>`). Fuente: code.claude.com/docs.
- **Antigravity 2.0**: `.agents/skills/<x>/SKILL.md`; reglas en `AGENTS.md`/`GEMINI.md`/`.agents/rules/*.md` (siempre activas, presupuesto de 20k tokens); **sin subagentes en archivo** (solo `define_subagent` en sesión, con flags como `enable_write_tools`); `.agents/hooks.json` con `PreInvocation` (antes de **cada** llamada al modelo, síncrono, `cmd /c` en Windows, cwd = carpeta de `hooks.json`, stdout JSON `{"injectSteps": [...]}`) y **sin evento de inicio de sesión**; MCP solo en `~/.gemini/config/mcp_config.json` (global) o en plugins (`.agents/plugins/<x>/mcp_config.json`), no en `.agents/mcp_config.json`. Fuente: documentación local de Antigravity.

## Decisión
1. **Generador en el motor para herramientas conocidas.** `aos adapt-native <tool>` genera los nativos de forma determinista para `claude-code` y `antigravity`. Todo vive en el paquete `dass_aos/native/`: una clase base (`base.py`, `NativeAdapter`) orquesta, módulos comunes leen `.aos/` (`sources.py`), escriben de forma segura (`files.py`) y gestionan manifiesto y hash (`manifest.py`), y cada herramienta es un módulo que hereda de la base y solo define rutas, mapeo de herramientas y formato (`claude.py`, `antigravity.py`). Añadir una herramienta = un módulo + una línea en el registro de `__init__.py`.
2. **La base garantiza las reglas de ADR-004** (puntos 5-8), que siguen vigentes: lectura de `.aos/` renderizado (base + `.local.md`), marcador `DASS-AOS-GENERATED`, nunca tocar archivos sin marcador, merge de JSON conservando lo ajeno, borrado solo de lo generado que ya no corresponde, bloque de `.gitignore` por herramienta, manifiesto con `source_hash` y `enforcement`, idempotencia.
3. **Aprobación humana sin agente.** Sin `--yes`, el comando muestra el diff de hooks, permisos y MCP y no los escribe; subagentes y skills se escriben siempre. `--dry-run` no escribe nada.
4. **MCP: reutilizar los de usuario.** El generador no crea servidores MCP; detecta cómo están registrados los de `.aos/mcp-config.json` en la configuración de usuario de la herramienta y registra el mapeo en el manifiesto. Si falta alguno, avisa y lo deja como `convention`. *Enmienda 2026-10-16:* en Claude Code los roles se restringen con `disallowedTools` (lo que el rol no tiene) en vez de una allowlist `tools`, así los MCP se heredan sin depender de su nombre registrado; la detección queda solo para el manifiesto y el aviso.
5. **Formato verificado como dato.** Cada adaptador declara la versión de la herramienta, la fecha y las fuentes con que se verificó su formato; van al manifiesto. Si la herramienta cambia de formato, se actualiza el adaptador (con sus tests), no se reinterpreta en cada máquina.
6. **La skill `adapt-native` queda como respaldo** para herramientas sin adaptador (Codex, Cursor, OpenCode, Gemini CLI…) y para investigar un cambio de formato antes de actualizar un adaptador. Para herramientas con adaptador, la skill indica ejecutar el comando.
7. **Antigravity:** sin subagentes en archivo, los roles quedan en `.aos/agents/` y el bloque gestionado de `GEMINI.md` indica delegar con `define_subagent` usando el rol como prompt y `enable_write_tools: false` cuando el rol no tiene `edit`/`write` (`enforcement.tools: convention`). El inicio de sesión se emula con un hook `PreInvocation` que llama a `aos refresh --hook antigravity`, el cual solo inyecta el refresco en la primera invocación de cada conversación y devuelve `{}` en las demás (`enforcement.session_start: native-emulated`). *Enmienda 2026-10-16:* no se genera `.agents/rules/*.md`: la documentación local de Antigravity 2.0 solo documenta reglas en `GEMINI.md`/`AGENTS.md` y en plugins.

## Alternativas descartadas
- **Mantener solo la skill (ADR-004):** no determinista, no testeable; ya falló en la herramienta de prueba.
- **Partir la skill en una spec por herramienta (`adapt-native-claude.md`, `adapt-native-antigravity.md`):** sigue dependiendo de la interpretación del agente y duplica el mapeo que el adaptador ya tiene en código y tests.
- **Una flag por herramienta (`--antigravity`, `--claude`):** el argumento posicional `<tool>` escala sin tocar el parser.
- **Roles como reglas de Antigravity (`.agents/rules/<rol>.md`):** siempre activas; meterían los 6 roles en cada conversación y consumirían el presupuesto de reglas.
- **MCP en un plugin de Antigravity / `.mcp.json` en Claude Code:** duplica los servidores ya registrados por el usuario.

## Consecuencias
- A favor: resultado determinista, idempotente y con tests; el agente ya no puede inventar nombres ni saltarse pasos; se puede usar sin agente (CI, `aos init`).
- En contra: el motor vuelve a tener código por herramienta, que caduca con cada cambio de formato (mitigado por versión y fuentes en el manifiesto y por la skill de respaldo). Leer la configuración de usuario para detectar MCP es la parte más frágil.
- ADR-004 sigue vigente en todo lo demás: vocabulario neutral de `tools_allowed`, `.aos/mcp-config.json` neutral, manifiesto, nativos fuera de git, seguridad de escritura y `convention` cuando no hay soporte nativo.

## Condiciones de Revocación
Solo puede ser supersedido por otro ADR que lo declare explícitamente.
