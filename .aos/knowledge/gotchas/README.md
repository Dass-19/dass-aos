# Trampas y Gotchas — Errores Resueltos y Límites Conocidos

Cada archivo en este directorio es una nota atómica que documenta un aprendizaje o trampa arquitectónica:

```yaml
---
id: YYYYMMDDHHmm
title: Título descriptivo corto
severity: low | medium | high
tags: []
---
```

## Estructura Recomendada
- **Síntoma**: Qué error o comportamiento inesperado ocurrió.
- **Causa Raíz**: Por qué ocurrió el fallo.
- **Resolución**: Cómo se solucionó.
- **Prevención**: Regla práctica para no volver a tropezar con la misma piedra.

Los agentes **deben** consultar este directorio al inicio de cada sesión (`aos refresh`) y antes de iniciar una tarea (`pre-task`).
El comando `aos refresh` extrae automáticamente las trampas más recientes.
