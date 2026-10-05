---
id: 202610051445
title: "Manejo de codificación UTF-8 en consolas Windows (cp1252)"
severity: high
tags: [windows, python, encoding, cli]
---

# Trampa: Fallo de codificación en consolas de Windows (UnicodeEncodeError)

## Síntoma
Al imprimir caracteres Unicode como flechas `→` o emojis en consolas de Windows con codificación estándar (cp1252 / latin-1), los scripts de Python crasheaban inmediatamente con `UnicodeEncodeError`.

## Causa Raíz
Python 3 en terminales de Windows no configura UTF-8 de forma predeterminada para `sys.stdout` y `sys.stderr` a menos que se fuerce explícitamente o se use `PYTHONIOENCODING=utf-8`.

## Resolución
Se implementó `configure_utf8_output()` en `dass_aos/constants.py` que reconfigura `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` al inicio de cada comando del CLI.

## Prevención
Cualquier script o comando nuevo del CLI debe invocar `configure_utf8_output()` antes de enviar texto formateado a la salida estándar.
