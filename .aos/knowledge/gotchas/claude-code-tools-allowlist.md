---
id: 202610061800
title: "Claude Code: la allowlist de subagentes excluye MCP y no restringe Bash por prefijo"
severity: medium
tags: [claude-code, adapt-native, subagents, mcp]
---

# Trampa: traducir `tools_allowed` a `.claude/agents/*.md`

## Síntoma
1. Un subagente con `tools: Read, Grep, Bash` no ve ninguna herramienta MCP.
2. `tools: Bash(git *)` no funciona, y en `disallowedTools` elimina **todo** Bash.
3. Con `codebase-memory-mcp` o el plugin context7 ya instalados a nivel de usuario, un `.mcp.json` con `codebase-memory`/`context7` arranca servidores duplicados.

## Causa Raíz
- `tools` es una allowlist: los MCP solo entran si se listan como `mcp__<servidor>` (o `mcp__*`).
- La restricción de comandos Bash solo existe en `permissions` de `settings*.json`, y aplica a toda la sesión, no por subagente.
- El nombre del servidor en la allowlist es el nombre **con el que está registrado** (p. ej. `mcp__codebase-memory-mcp`, `mcp__plugin_context7_context7`), no el de `.aos/mcp-config.json`.

## Solución
- Incluir siempre los `mcp__<servidor>` correspondientes a cada `mcp:<x>`.
- `shell:<prefijo>` → `Bash, PowerShell` + restricción como texto en el cuerpo; manifiesto `shell_prefix: convention`.
- Si los servidores ya existen a nivel de usuario/plugin, reutilizarlos (no generar `.mcp.json`) y registrar el mapeo en `.aos/native/claude-code.json`.
- Fuente: https://code.claude.com/docs/en/sub-agents (verificado 2026-10-06).
