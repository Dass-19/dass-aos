---
id: 202611161330
title: "Atribuir tokens a un proyecto: workspace real de Antigravity y transcripts de subagentes de Claude Code"
severity: medium
tags: [telemetry, tui, tokens, antigravity, claude-code, windows]
---

# Trampa: la pestaña Tokens mezclaba proyectos y omitía consumo propio

## Síntoma
En `aos tui` (pestaña 7) los totales no correspondían solo a este proyecto:
1. Entraban conversaciones de Antigravity de otros proyectos que solo *mencionaban* la ruta (p. ej. una de `contable_innotech`).
2. Faltaban conversaciones propias (las de subagentes y las que no estaban entre las 15 más recientes).
3. Faltaban los transcripts de subagentes de Claude Code y las sesiones de Claude anteriores a las 5 más recientes.

## Causa Raíz
1. Antigravity se emparejaba buscando la ruta del proyecto en el texto del transcript. El dato fiable es `workspace_uris` en `~/.gemini/antigravity/conversation_summaries.db` (tabla `conversation_summaries`), con URIs del tipo `file:///c%3A/Users/...`; `url2pathname` no reconoce la unidad si el `:` sigue codificado, así que hay que aplicar `unquote` antes.
2. Claude Code guarda los subagentes en `~/.claude/projects/<slug>/<session-id>/subagents/*.jsonl`, fuera del `glob("*.jsonl")` del directorio.
3. El `<slug>` de Claude Code sustituye **todo** carácter no alfanumérico por `-` (también `_`, `.` y espacios), no solo `:` y separadores.

## Resolución
- `_antigravity_workspace_conversations` (`dass_aos/telemetry.py`) lee el índice en modo solo lectura; la heurística por texto queda solo como respaldo si la BD no existe o está bloqueada.
- Los tokens se suman sobre **todas** las sesiones del proyecto más sus subagentes; la lista de sesiones sigue mostrando solo las más recientes.
- Una llamada a la API (`message.id:requestId`) se cuenta una sola vez entre sesiones, porque una sesión reanudada puede repetirla.
- Test: `test_tokens_are_scoped_to_this_project_workspace`.
