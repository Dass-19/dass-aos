---
id: 202610051600
type: decision
status: vigente
created: 2026-10-05
---

# ADR-003: Base genérica del motor + agregados locales para agentes y skills

## Contexto
Los roles (`agents/*.md`) y skill specs (`skills/specs/*.md`) son genéricos y stack-agnósticos a propósito: deben servir en cualquier proyecto. Hasta v0.4.0, `aos init` los copiaba una sola vez a `.aos/` y nunca más los tocaba. Consecuencias:
1. Las mejoras del motor no llegaban a los proyectos ya inicializados.
2. El proyecto no tenía dónde poner sus reglas propias sin editar la copia, y al editarla perdía cualquier actualización futura.

## Decisión
1. **El motor es dueño de la base.** `.aos/agents/<rol>.md` y `.aos/skills/specs/<skill>.md` de los roles/skills del motor son archivos **generados**: `aos sync` (y `aos init`) los regeneran a partir de `dass_aos/templates/`. Llevan un marcador `<!-- DASS-AOS-GENERATED ... -->`.
2. **El proyecto es dueño de los agregados.** Lo específico del proyecto va en `<rol>.local.md` / `<skill>.local.md`, al lado del generado. `sync` lo anexa al final del generado bajo "Agregados del proyecto". Nunca lo modifica.
3. **Roles/skills propios del proyecto** (sin template en el motor) son 100% del proyecto: `sync` no los toca.
4. **Sin pérdida de datos.** Si un archivo base existe sin marcador y su contenido difiere del template actual (editado a mano o de una versión anterior), `sync` no lo sobreescribe y avisa para mover los cambios a `.local.md`.
5. **Skills condicionales.** Una skill spec puede declarar `applies_when: [globs]` (lista JSON en una línea, relativos a la raíz del proyecto). Las instrucciones generadas solo listan las skills sin ese campo o cuyos globs encuentran algo.

## Alternativas descartadas
- **Copiar una vez (estado anterior):** sin camino de actualización.
- **Editar la copia + merge de 3 vías en `sync`:** más código y conflictos que resolver a mano; no justificado para Markdown.
- **No copiar y apuntar al paquete instalado:** los agentes leen archivos del repo; una ruta a `site-packages` no es portable entre máquinas.

## Consecuencias
- A favor: actualizaciones del motor llegan con `pip install -U dass-aos && aos sync`; lo propio del proyecto queda aislado y versionado en su repo.
- En contra: editar un generado a mano se pierde en el siguiente `sync` (mitigado por el marcador y el aviso del punto 4).

## Condiciones de Revocación
Solo puede ser supersedido por otro ADR que lo declare explícitamente.
