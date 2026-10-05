---
id: 202610051700
title: "Archivos del motor fuera del paquete o asumidos en el proyecto destino"
severity: high
tags: [packaging, pip, setuptools, bootstrap]
---

# Trampa: el motor solo funciona desde el repo clonado

## Síntoma
Con `pip install -e .` (o desde el repo) todo pasa. Con `pip install` normal, `aos init` crea las carpetas de `.aos/` pero vacías: sin agentes, skills ni plantillas. Y en proyectos destino el hook de git `python aos.py verify || exit 1` bloqueaba todos los commits.

## Causa Raíz
- Las plantillas vivían en la raíz del repo y se resolvían con una ruta relativa al código (`ENGINE_ROOT = parent.parent`). `pyproject` solo empaquetaba `dass_aos*`: fuera del repo esa ruta apunta a `site-packages/`.
- Instrucciones, hook y shims asumían archivos del repo del motor (`aos.py`, `parents[2]/dass_aos`) que no existen en el proyecto destino.

## Resolución
- Plantillas en `dass_aos/templates/` + `[tool.setuptools.package-data] dass_aos = ["templates/**/*"]`.
- Comandos como `aos <cmd>` / `python -m dass_aos <cmd>`; hook que sale 0 si falta Python o dass-aos.

## Prevención
- Todo archivo que el motor lea en runtime va **dentro** de `dass_aos/` y declarado en `package-data`.
- Nada de lo que se copia a un proyecto puede depender del repo del motor (solo stdlib o `python -m dass_aos`).
- Antes de un release: `pip install .` (no editable) en un venv limpio → `aos init` en un repo vacío → commit.
