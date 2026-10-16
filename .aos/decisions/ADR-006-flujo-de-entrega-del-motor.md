---
id: 202610161400
type: decision
status: vigente
created: 2026-10-16
---

# ADR-006: Flujo de entrega en el motor (fases con gates, revisión adversarial y verificación en vivo)

## Contexto
Tres proyectos llegaron por separado al mismo flujo de trabajo, cada uno con su propia copia de las specs:
- **password-manager**: `phased-delivery`, `adversarial-review` y `visual-qa-egui`, más los roles `adversarial-verifier` y `visual-qa`. Esta revisión encontró 10 problemas reales en el backend y 24 en la UI que las pruebas no detectaban. La app de escritorio se maneja sin robar el foco: `PrintWindow` y `PostMessage` en lotes.
- **cms-crai**: la versión más madura, usada en los planes 001–008, con lentes por dominio, gates con comandos exactos y una base QA desechable. El navegador se maneja con `playwright-cli` a 1400 y 375 px, y la evidencia queda en `.playwright-cli/`. Ahí salió la regla de que una prueba tiene que verse fallar.
- **finDass**: verificación web ligera, con el dev server, una sesión firmada localmente y `playwright-cli`. La evidencia queda escrita en el plan.

El motor solo traía un ciclo de vida genérico (`verify`/`scan`) sin gates por fase, sin revisión que descarte falsos positivos y sin manera de comprobar la app en marcha. Cada proyecto lo reimplementaba, y los proyectos nuevos empezaban sin nada de esto.

`playwright-cli` (`@playwright/cli`, verificado el 2026-10-16 en playwright.dev/agent-cli con la versión 0.1.22):
- Es headless por defecto.
- Funciona por sesiones con nombre (`-s=<nombre>`).
- Trae una skill oficial que se instala con `playwright-cli install --skills [=claude|=agents] [-g]`.

## Decisión
1. **El motor trae el flujo.** Se añaden tres skills, `phased-delivery`, `adversarial-review` y `live-verify`, y un único rol nuevo, `adversarial-verifier`. Son genéricas. Lo propio de cada proyecto se escribe en su `.local.md` (ADR-003): lentes y qué buscar en cada una, gates con comandos, entorno desechable, anchos de pantalla y scripts de escritorio.
2. **El que implementa se corrige.** El bucle de `live-verify` (levantar, ejercer, observar, corregir, como mucho 3 rondas) lo ejecuta `app-builder` al cerrar cada fase. `qa-tester` lo usa para obtener evidencia sin tocar el código de producción. No se crea un rol `visual-qa`: en password-manager su contenido era propio del proyecto, y ahora va en `live-verify.local.md`.
3. **Revisar no es corregir.** Los revisores por lente y el verificador no editan nada. Solo se corrige lo confirmado, lo hace un único agente, y cada corrección deja una comprobación que se haya visto fallar con el código anterior.
4. **El navegador se explora, no se convierte en suite.** La vía web usa `playwright-cli`, con su skill oficial instalada globalmente (`-g`). El motor no la copia y no la instala por proyecto. `aos refresh` avisa si falta el CLI en un proyecto con frontend web. Las suites `@playwright/test` y el Playwright MCP quedan fuera.
5. **Escritorio:** con los scripts del proyecto (`.aos/skills/bin/<x>/`) o con el control de escritorio de la herramienta, si lo tiene. Siempre con datos desechables.
6. **Entorno desechable obligatorio** para todo lo que escribe datos. Se declara en un solo sitio, `live-verify.local.md`, y las demás skills y roles remiten a él. Las cuentas reales se usan solo en lectura y con autorización. La evidencia se queda fuera de git: `aos init` y cada `aos sync` añaden `.playwright-cli/` a `.gitignore` si falta.
7. **Hooks y plantillas de plan son del proyecto.** `.aos/hooks/*.md` y `.aos/plans/templates/*.md` se copian una vez y `aos sync` no los toca, porque llevarlos al esquema de marcador metería el marcador "no editar" en cada plan nuevo. Para recibir la versión nueva del motor: se borra el archivo y se ejecuta `aos init` (sin `--force`, no toca `config.json`). Las skills sincronizadas (`phased-delivery` exige un `Gate:` por fase) cubren el flujo aunque la plantilla sea antigua.

## Alternativas descartadas
- **Dejar cada flujo en su proyecto:** se divide en copias distintas (cms está una versión por detrás de cms-crai) y los proyectos nuevos empiezan sin él.
- **Copiar las specs de cms-crai tal cual:** mezclan reglas de dominio (`csrf_check()`, `craicms_qa`, Astro) con el flujo. En un proyecto distinto serían ruido o directamente instrucciones erróneas.
- **Suites `@playwright/test`:** cms-crai las descartó en su plan 004. El valor está en que el agente vea la app y se corrija, no en mantener una suite E2E.
- **Copiar la skill de playwright-cli en el motor:** son 489 líneas que mantiene Playwright y se quedarían obsoletas. Basta con instalarla globalmente una vez.

## Consecuencias
- A favor: cualquier proyecto con `aos init` arranca con el flujo. Las mejoras se hacen una vez en el motor, y los proyectos solo mantienen su `.local.md`.
- En contra: hay 7 roles y 3 skills más en el bloque gestionado. Los proyectos que ya tienen su propia `adversarial-review.md` o `phased-delivery.md` sin marcador verán "OMITIDO" en `aos sync` hasta que muevan lo suyo a `.local.md`.

## Condiciones de Revocación
Solo puede ser supersedido por otro ADR que lo declare explícitamente.
