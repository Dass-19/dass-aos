---
id: 202610061800
title: "Claude Code: la allowlist de subagentes excluye MCP; restringir con disallowedTools"
severity: medium
tags: [claude-code, adapt-native, subagents, mcp]
updated: 2026-10-16
---

# Trampa: traducir `tools_allowed` a `.claude/agents/*.md`

## Síntoma
1. Un subagente con `tools: Read, Grep, Bash` no ve ninguna herramienta MCP.
2. Para incluirlas hay que adivinar con qué nombre están registradas (`mcp__codebase-memory-mcp`, `mcp__plugin_context7_context7`…), y eso cambia con cada máquina.
3. `tools: Bash(git *)` no funciona, y en `disallowedTools` elimina **todo** Bash.
4. Con `codebase-memory-mcp` o el plugin context7 ya instalados a nivel de usuario, un `.mcp.json` con `codebase-memory`/`context7` arranca servidores duplicados.

## Causa Raíz
- `tools` es una allowlist: sin ella el subagente hereda todo, incluidos los MCP. `disallowedTools` quita solo lo que nombra (https://code.claude.com/docs/en/sub-agents, verificado el 2026-10-16).
- La restricción de comandos Bash solo existe en `permissions` de `settings*.json`, y aplica a toda la sesión, no por subagente.

## Solución (`aos adapt-native claude-code`, ADR-005)
- No escribir `tools`. Poner en `disallowedTools` lo que el rol **no** tiene del vocabulario neutral (p. ej. `reviewer` → `Edit, NotebookEdit, Write, WebFetch, WebSearch`). Así los MCP se heredan sin tener que conocer su nombre.
- `shell:<prefijo>` y el subconjunto de `mcp:<x>` van como texto en el cuerpo. En el manifiesto: `shell_prefix: convention` y `mcp_subset: convention`.
- Reutilizar los MCP de usuario o plugin (no generar `.mcp.json`). El generador solo detecta si existen, para el manifiesto y para avisar.
