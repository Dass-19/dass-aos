---
id: 202610061600
type: skill-spec
status: evergreen
name: "adapt-native"
description: "Traduce .aos/ (roles, skills, hooks, MCP, tools_allowed) a los formatos nativos de la herramienta de IA en uso, verificando su documentación actual."
runtime: agent
entrypoint: "instrucciones para el agente (sin comando)"
inputs:
  - name: tool
    type: string
    description: "Identificador kebab-case de la herramienta en uso (claude-code, antigravity, codex, cursor, opencode, gemini-cli…)"
    required: true
outputs:
  format: "archivos nativos + .aos/native/<tool>.json"
created: 2026-10-06
updated: 2026-10-06
---

# Skill: adapt-native

> **Claude Code y Antigravity tienen generador determinista: ejecuta `aos adapt-native <tool> --yes` y no sigas esta skill** (ADR-005). Esta skill es el respaldo para el resto de herramientas y para investigar un cambio de formato antes de actualizar un adaptador.
>
> La ejecuta **el agente de la herramienta en uso** (no el CLI) cuando no existe `.aos/native/<tool>.json` o `aos refresh` / `aos sync` lo marcan como DESACTUALIZADO.
> Decisión y vocabulario en ADR-004. `.aos/` es la única fuente de verdad: lo generado aquí es desechable y regenerable.

## 1. Identificar la herramienta
Determina en qué herramienta corres (y su versión si es posible). Usa un identificador kebab-case estable para `<tool>`.

## 2. Verificar el formato actual (obligatorio)
1. Consulta la documentación **con context7** (servidor MCP `context7`).
2. Si context7 no la cubre, está desactualizada o tienes **cualquier duda**, busca en la **web** la documentación oficial de la herramienta.
3. **Nunca escribas un formato de memoria.** Anota cada URL consultada para el manifiesto.

Qué averiguar: rutas y frontmatter de subagentes, rutas de skills (`SKILL.md`, estándar agentskills.io), formato de hooks y si existe evento de inicio de sesión, formato de servidores MCP (local y remoto), cómo restringir herramientas por agente (lista de permitidas y/o de bloqueo), qué archivo es personal/no versionado.

## 3. Generar desde `.aos/`
Lee siempre la versión renderizada (base + `<nombre>.local.md`).

| Fuente | Destino nativo |
|---|---|
| `.aos/agents/<rol>.md` | un subagente por rol: `name`, `description`, herramientas traducidas de `tools_allowed`, cuerpo del rol |
| `.aos/skills/specs/<skill>.md` | una skill por spec **que aplique** (`applies_when`; la lista vigente está en el bloque gestionado de CLAUDE.md/AGENTS.md). No generes `adapt-native` ni las que no aplican; borra las generadas que dejaron de aplicar |
| `.aos/mcp-config.json` | servidores MCP nativos. `{"command","args","env"}` = local; `{"url"}` = remoto (traduce la clave: `type: http` + `url`, `serverUrl`, etc.) |
| `.aos/hooks/session-start.md` | hook de inicio de sesión que ejecute `aos refresh`, con fallback `python -m dass_aos refresh`, **nunca bloqueante** y sin depender del PATH. Si la herramienta no tiene evento de inicio, no lo simules con eventos por llamada: déjalo como convención |

### Traducción de `tools_allowed` (vocabulario neutral, ADR-004)
`read`, `search`, `edit`, `write`, `shell`, `shell:<prefijo>`, `web`, `mcp:<servidor>`.
- Mapea cada valor a los **nombres nativos exactos** que documenta la herramienta. Nunca copies el vocabulario neutral tal cual (`mcp:context7`, `search`) en un campo nativo; si un valor no tiene equivalente documentado, déjalo como texto y regístralo como `convention`. Para MCP usa el mecanismo nativo (nombre de herramienta MCP, campo de servidores MCP del agente, etc.). `shell:<prefijo>` → la forma nativa de restringir comandos si existe; si no, `shell` + la restricción como texto en el cuerpo del subagente.
- Cuidado: en algunas herramientas una lista de permitidas **excluye los MCP no listados**. Inclúyelos explícitamente o, si la herramienta tiene lista de bloqueo (p. ej. `disallowedTools`), bloquea solo el complemento cuando sea equivalente.
- Si la herramienta no puede restringir herramientas por agente, escribe la restricción como texto en el subagente/regla y registra `enforcement: "convention"`.

## 4. Reglas de escritura
- Todo archivo generado lleva **un solo** marcador `DASS-AOS-GENERATED` (comentario después del frontmatter si el formato exige frontmatter al inicio); quita el marcador que trae el `.md` de `.aos/` al copiar su cuerpo. En JSON/TOML, sin comentarios: identifica lo tuyo por nombre de servidor/hook y regístralo en el manifiesto.
- **Nunca modifiques un archivo sin marcador** ni configuración del usuario: fusiona (merge) JSON/TOML conservando todo lo ajeno.
- Prefiere los archivos personales/no versionados de la herramienta cuando existan (p. ej. `settings.local.json`).
- Borra solo archivos generados (con marcador o listados en el manifiesto anterior) que ya no correspondan.
- Añade a `.gitignore` cada ruta generada **y cada archivo personal en el que fusionaste algo** (p. ej. `.claude/settings.local.json`) dentro del bloque **de tu herramienta** (`<tool>` en el marcador). Créalo si no existe y reemplaza solo su contenido en cada ejecución. **No toques los bloques de otras herramientas.** Nunca ignores carpetas completas como `.claude/` o `.agents/`:
  ```gitignore
  # >>> DASS-AOS adapt-native: claude-code (generado, no editar) >>>
  .claude/agents/reviewer.md
  .claude/settings.local.json
  # <<< DASS-AOS adapt-native: claude-code <<<
  ```
- Después de escribir, comprueba con `git status` que nada de lo tuyo aparece como no versionado.

## 5. Aprobación humana
Antes de escribir **hooks, permisos o servidores MCP**, muestra el diff completo y espera aprobación explícita. Subagentes y skills se pueden escribir directamente.

## 6. Manifiesto
Escribe `.aos/native/<tool>.json` (local, ignorado en git). `source_hash` es la salida de `aos native-hash` (o `python -m dass_aos native-hash`) **después** de generar:
```json
{
  "tool": "claude-code",
  "tool_version": "x.y.z",
  "generated_at": "2026-10-06",
  "sources": ["https://…"],
  "files": [".claude/agents/reviewer.md", ".claude/settings.local.json#hooks.SessionStart"],
  "enforcement": {"tools": "native", "session_start": "native"},
  "source_hash": "<aos native-hash>"
}
```

## 7. Verificar
- Ejecuta `aos refresh`: tu herramienta debe aparecer "al día".
- Una segunda ejecución de esta skill sin cambios en `.aos/` no debe producir diferencias.
- Si descubriste algo no obvio del formato de la herramienta, documéntalo en `.aos/knowledge/gotchas/`.
