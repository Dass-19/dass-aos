---
id: 202610061500
type: decision
status: parcialmente supersedido por ADR-005
created: 2026-10-06
---

# ADR-004: Adaptación nativa delegada en el agente (`adapt-native`)

## Contexto
Cada herramienta de IA tiene su propio formato nativo para subagentes, skills, hooks, servidores MCP y restricción de herramientas, y esos formatos cambian entre versiones. Verificado el 2026-10-06:
- **Claude Code**: `.claude/agents/*.md` (`tools` allowlist que excluye MCP no listadas, `disallowedTools`), `.claude/skills/<x>/SKILL.md`, hooks con `SessionStart` en `.claude/settings*.json`, MCP en `.mcp.json`. Fuente: code.claude.com/docs.
- **Antigravity**: `.agents/rules/`, `.agents/skills/<x>/SKILL.md`, `.agents/agents/*.md` (`tools` allowlist), `.agents/mcp_config.json` (remotos con `serverUrl`), `.agents/hooks.json` **sin evento de inicio de sesión**; los workflows están deprecados en favor de skills. Fuente: antigravity.google/docs.
- `SKILL.md` sigue el estándar abierto agentskills.io: el formato se comparte, la ruta cambia por herramienta.

Mantener un generador en Python por herramienta no escala y queda obsoleto con cada versión.

## Decisión
1. **El motor no genera formatos nativos.** Los genera el agente de cada herramienta ejecutando la skill `adapt-native`, a partir de `.aos/` (fuente única, ADR-002/003).
2. **Documentación actual obligatoria.** `adapt-native` consulta primero context7 y, si no lo cubre o hay duda, la documentación oficial en la web. Nunca escribe formatos de memoria y cita sus fuentes.
3. **Contrato neutral de herramientas.** `tools_allowed` de cada rol usa solo este vocabulario (lo valida `aos sync`, que falla ante un valor desconocido):
   | Valor | Significado |
   |---|---|
   | `read` | leer archivos |
   | `search` | buscar archivos y contenido |
   | `edit` / `write` | modificar / crear archivos |
   | `shell` | cualquier comando |
   | `shell:<prefijo>` | solo comandos que empiezan por `<prefijo>` (p. ej. `shell:aos`, `shell:git`) |
   | `web` | búsqueda y lectura web |
   | `mcp:<servidor>` | herramientas de un servidor declarado en `.aos/mcp-config.json` |
   Las skills se invocan por `shell:aos …`; no tienen entrada propia. Si la herramienta admite lista de bloqueo (Claude Code `disallowedTools`) y la lista de permitidas dejaría fuera MCP, `adapt-native` puede traducir como bloqueo del complemento, siempre que el resultado sea equivalente.
4. **MCP neutrales** en `.aos/mcp-config.json`: `{"command", "args", "env"}` para locales y `{"url"}` para remotos; `adapt-native` los traduce (`url` → `serverUrl` en Antigravity, `type: http` en Claude Code…).
5. **Trazabilidad.** `adapt-native` escribe `.aos/native/<herramienta>.json` con fuentes consultadas, archivos generados, `enforcement` (`native` | `convention`) y `source_hash` (`aos native-hash`). `aos sync` y `aos refresh` avisan si el hash ya no coincide.
6. **Por desarrollador, fuera de git.** Los artefactos nativos y `.aos/native/` no se commitean: `aos init` ignora `.aos/native/` y `adapt-native` añade sus rutas generadas a un bloque marcado de `.gitignore` (nunca carpetas enteras como `.claude/`). Cada dev ejecuta `adapt-native` en su herramienta.
7. **Seguridad de escritura.** Marcador `DASS-AOS-GENERATED` en todo archivo generado; nunca se toca un archivo sin marcador; la configuración JSON/TOML se fusiona sin pisar la del usuario; hooks, permisos y MCP requieren aprobación humana del diff.
8. **Sin soporte nativo = convención.** Si la herramienta no puede restringir herramientas o no tiene hook de inicio (Antigravity), la regla queda como texto y el manifiesto lo declara `convention`.

## Alternativas descartadas
- **Generadores por herramienta en el motor:** N formatos que mantener y que caducan con cada versión.
- **Commitear los nativos:** acopla el repo a las herramientas de cada dev y a versiones concretas de formato.
- **Solo texto (estado 0.5.0):** nada se hace cumplir donde la herramienta sí podría.

## Consecuencias
- A favor: cero código por herramienta; las nuevas se soportan sin release; el formato siempre es el vigente.
- En contra: el resultado no es determinista ni testeable de forma unitaria (mitigado por el manifiesto, el hash, la aprobación humana y la prueba real por herramienta). Requiere un agente capaz de consultar documentación.

## Condiciones de Revocación
Solo puede ser supersedido por otro ADR que lo declare explícitamente.
