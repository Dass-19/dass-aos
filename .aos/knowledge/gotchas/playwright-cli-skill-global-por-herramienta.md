---
id: 202610161500
title: La skill global de playwright-cli no llega a Antigravity, y screenshot --filename guarda relativo al cwd
severity: low
tags: [playwright, live-verify, antigravity, claude-code]
---

## Síntoma
- `playwright-cli install --skills=agents -g` instala en `~/.agents/skills/playwright-cli`, pero Antigravity no ve la skill.
- `playwright-cli screenshot --filename=x.png` deja la captura en el directorio actual, no en `.playwright-cli/` con los snapshots y los logs de consola. Puede acabar en git.

## Causa Raíz
- La raíz global de personalización de Antigravity es `~/.gemini/config/`, no `~/.agents/`. Solo descubre skills en `.agents/skills/` del workspace o en las rutas de un `skills.json` (documentación local: `agy-customizations/docs/json_configs.md`).
- Claude Code sí lee `~/.claude/skills/` (`install --skills -g`).
- `--filename` es relativo al cwd; solo los snapshots y los logs van solos a `.playwright-cli/` (verificado con 0.1.22 el 2026-10-16).

## Resolución
- Antigravity: no hace falta la skill. `playwright-cli --help` imprime la ruta de la `SKILL.md` que trae el paquete npm, y `live-verify` indica leerla. Si se quiere la skill registrada, se puede añadir `~/.agents/skills` como entrada en `~/.gemini/config/skills.json` (sin probar).
- Capturas: `--filename=.playwright-cli/<pantalla>-<estado>-<ancho>.png`.

## Prevención
- `aos refresh` solo comprueba la skill en Claude Code (`~/.claude/skills/playwright-cli` o la del proyecto). En las demás herramientas comprueba únicamente el CLI.
