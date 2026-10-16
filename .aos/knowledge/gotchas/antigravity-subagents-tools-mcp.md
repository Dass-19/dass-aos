---
id: 202610061900
title: "Antigravity 2.0: sin subagentes en archivo, sin evento de inicio, MCP solo global y stdin del hook en cp1252"
severity: medium
tags: [antigravity, adapt-native, subagents, mcp, hooks]
updated: 2026-10-16
---

# Trampa: traducir `.aos/` a Antigravity 2.0

## Síntoma
1. `.agents/agents/<rol>.md` generados según antigravity.google/docs/subagents: `subagent "reviewer" not found`. El agente acaba usando `define_subagent` y el `tools` del archivo no se aplica.
2. `grep_search` aparece en el ejemplo de la web pero "no existe" en el runtime.
3. Un `.agents/mcp_config.json` con `codebase-memory` no tiene efecto: se usa la definición global con el mismo nombre.
4. Las reglas en `.agents/rules/*.md` no aparecen en la documentación local: no se puede contar con que se carguen.
5. El hook `PreInvocation` recibe por stdin un JSON con BOM o con rutas acentuadas, y `json.loads(sys.stdin.read())` falla en Windows (stdin en cp1252). Resultado: `{}` en todas las llamadas.

## Causa Raíz
- La documentación que vale es la local (`~/.gemini/antigravity/builtin/skills/agy-customizations/docs/`), no la web. Allí:
  - Skills: `.agents/skills/<x>/SKILL.md`, o rutas declaradas en `skills.json`. La raíz global es `~/.gemini/config/`, no `~/.agents/`.
  - Reglas: solo `GEMINI.md` y `AGENTS.md` (sin frontmatter, siempre activas, 20k tokens en total) y las de los plugins.
  - Hooks: `.agents/hooks.json`. `PreInvocation` se ejecuta antes de **cada** llamada al modelo, en `cmd /c` en Windows y con el cwd en la carpeta de `hooks.json`. No hay evento de inicio de sesión.
  - MCP: `~/.gemini/config/mcp_config.json` (global) o plugins.
- Python decodifica `sys.stdin` con la página de códigos de la consola, y algunos shells anteponen un BOM.

## Solución (`aos adapt-native antigravity`, ADR-005)
- Solo se generan skills y el hook. Los roles se delegan con `define_subagent` siguiendo el bloque gestionado de `GEMINI.md`, que lista los roles sin escritura (`enable_write_tools: false`).
- Inicio de sesión emulado: `aos refresh --hook antigravity` inyecta el refresco una vez por `conversationId` (guarda los vistos en `.aos/native/antigravity-seen.txt`) y devuelve `{}` en las demás llamadas o ante cualquier error.
- El hook lee `sys.stdin.buffer` y decodifica con `utf-8-sig`.
- MCP: no se generan servidores por proyecto. Si falta uno en la configuración global, el generador avisa y lo deja como convención.

## Prevención
- Antes de tocar el adaptador, contrastar con la documentación local de la versión instalada, no con la web.
- Probar el hook como lo ejecuta Antigravity: `'{"conversationId":"x"}' | cmd /c "<command>"` desde `.agents/`.
