---
id: 202610061700
title: "Escáneres instalados en un venv no activado (Windows)"
severity: medium
tags: [windows, python, venv, semgrep, checkov, cli]
---

# Trampa: `aos scan` no encuentra Semgrep/Checkov instalados con `dass-aos[scan]`

## Síntoma
Con `pip install "dass-aos[scan]"` en un venv y ejecutando `venv/Scripts/aos` sin activar el venv:
1. `aos scan` decía "Semgrep is not installed" aunque lo estaba.
2. Ya encontrado, Checkov fallaba con `ModuleNotFoundError: No module named 'checkov'`.

## Causa Raíz
1. `shutil.which` solo busca en el PATH, y `venv/Scripts` no está en el PATH si el venv no está activado.
2. En Windows, `checkov.cmd` lanza el `python` del PATH (el global), no el del venv donde está instalado Checkov.

## Resolución
- `check_tool_installed` (`dass_aos/scanners.py`) busca también junto a `sys.executable`.
- `run_checkov` usa `sys.executable -m checkov.main` cuando Checkov es importable desde el Python de `aos`.

## Prevención
Para herramientas Python que el motor ejecuta, preferir `sys.executable -m <módulo>` a los lanzadores de consola. Semgrep en Windows nativo funciona (beta) con `PYTHONUTF8=1`.
