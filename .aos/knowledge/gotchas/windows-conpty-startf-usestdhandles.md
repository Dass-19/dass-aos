---
title: "Windows ConPTY: CreateProcessW requiere STARTF_USESTDHANDLES con handles nulos si el padre tiene pipes"
severity: high
status: abierta
created: 2026-11-18
tags: [windows, conpty, pty, tui]
---

# Windows ConPTY: `CreateProcessW` requiere `STARTF_USESTDHANDLES` con handles nulos si el padre tiene pipes

## Síntoma
Al crear un pseudo-terminal en Windows con `CreatePseudoConsole` y lanzar un proceso hijo mediante `CreateProcessW(..., EXTENDED_STARTUPINFO_PRESENT, ...)` asociado a `PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE`, si el proceso padre (por ejemplo, un test runner o subproceso de agente) tiene `stdout`/`stderr` redirigidos a pipes, el hijo hereda los handles estándar del padre en lugar de conectarse al ConPTY. Su salida se imprime en la consola del padre y el pipe de lectura del ConPTY solo recibe la secuencia de inicialización `\x1b[?9001h\x1b[?1004h`.

## Causa
En Windows, `CreateProcessW` prioriza los handles estándar heredables del padre a menos que `STARTUPINFOEXW.StartupInfo.dwFlags` incluya `STARTF_USESTDHANDLES` (`0x00000100`) con `hStdInput = hStdOutput = hStdError = NULL` (`0`), lo que fuerza al subsistema ConPTY a enlazar los flujos estándar del proceso hijo al pseudo-terminal.

## Mitigación
En `dass_aos/tui/pty_terminal.py` (`PtySession._start_win_conpty`), establecer siempre:
```python
si.StartupInfo.dwFlags = 0x00000100  # STARTF_USESTDHANDLES con handles NULL
```
junto con `bInheritHandles = False` y `EXTENDED_STARTUPINFO_PRESENT = 0x00080000`.
