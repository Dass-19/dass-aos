# ADR-011: Terminal PTY/ConPTY + Emulador VT100 Embebido Estilo Herdr en `aos tui`

- **Estado**: Aceptado
- **Fecha**: 2026-11-18
- **Contexto**:
  Para supervisar e interactuar con sesiones de agentes (`claude`, `agy`, `codex`, `opencode`, etc.) desde `aos tui` igual que en Herdr (`https://herdr.dev/`), no basta con ejecutar comandos puntuales `claude -p`: el usuario necesita abrir cualquier sesión en un panel de terminal interactivo real dentro de la TUI, ver en tiempo real la interfaz CLI nativa del agente (colores ANSI/TrueColor, spinners, diffs, menús `/voice`, diálogos de permisos/preguntas) y teclear directamente en ella (**Terminal Mode** vs **Navigate Mode**), detectando automáticamente los estados `working`, `blocked` (`pending`) e `idle`/`done` a partir del buffer VT100 y secuencias OSC.
- **Decisión**:
  1. Implementar `dass_aos/tui/pty_terminal.py` usando únicamente stdlib de Python:
     - **Windows**: `CreatePseudoConsole`, `ResizePseudoConsole`, `ClosePseudoConsole` y `CreateProcessW` vía `ctypes.windll.kernel32` con `STARTF_USESTDHANDLES = 0x00000100` y handles nulos para que el proceso hijo se enlace al ConPTY incluso cuando el proceso padre tiene pipes redirigidos.
     - **Unix (Linux/macOS)**: `pty.openpty()` + `fcntl.ioctl(..., termios.TIOCSWINSZ)` + `subprocess.Popen`.
  2. Incluir un emulador de pantalla **VT100/ANSI 2D (`VtScreen`)** en `dass_aos/tui/pty_terminal.py` que procesa cursores (`CSI H/A/B/C/D/G/J/K`), scroll, pantalla alternativa (`?1049h/l`), colores SGR (16, 256 y 24-bit TrueColor), títulos OSC (`\e]0;`, `\e]2;`) y protocolo de estado OSC 7501 (`\e]7501;state=...`), renderizando el viewport a objetos `rich.text.Text` con el cursor resaltado.
  3. Incorporar el motor de detección de estado en pantalla (`detect_terminal_agent_state`) basado en las reglas verificadas de Herdr (`claude.toml` y `agy.toml`): título OSC con spinner braille/medio círculo o pie `esc to interrupt`/`esc to cancel` → `working`; diálogos `Do you want to proceed?`, `Enter to confirm · Esc to cancel`, `Navigate · tab Amend`, `Navigate · esc Skip` → `pending` (`blocked`); prompt `❯` → `idle`.
  4. En la pestaña `3 · Agentes & Tasks`, integrar el widget interactivo `AgentTerminalWidget` que abre/adjunta en un PTY vivo cualquier sesión seleccionada (`claude --resume <id>`, `claude`, `agy` o shell), reenvía teclas crudas en **Modo Terminal** y sale al **Modo Navegación** con `Ctrl+G` (o `Ctrl+B`), permitiendo alternar con `Tab`/`Vista` entre el **Terminal en Vivo (PTY)** y el **Inspector (Timeline + Logs)**.
- **Consecuencias**:
  - Cero dependencias compiladas nuevas: funciona out-of-the-box en Windows 10/11, Linux y macOS.
  - Experiencia idéntica a Herdr dentro de `aos tui`: el usuario ve trabajar la sesión CLI del agente en vivo y la controla desde el mismo panel.
