# Hook de Post-Tarea (Post-Task)
> Obligatorio antes de dar una tarea activa por concluida.

1. **Verificación**:
   - Ejecutar los linters y pruebas del proyecto:
     ```bash
     aos verify
     ```
   - Ejecutar los escáneres de seguridad:
     ```bash
     aos scan --dry-run
     ```
   - Si se modificó un contrato HTTP, regenerar los clientes tipados:
     ```bash
     aos generate-client --contract .aos/contracts/http/<especificacion>.yaml --output <directorio-cliente>
     ```

2. **Verificación en Vivo y Revisión (ADR-008)**:
   - Si se tocó UI, API, CLI o una app de escritorio: skill `live-verify` (levantar, ejercitar, mirar la evidencia y corregir, hasta 3 rondas).
   - Si el cambio tiene **riesgo nombrado** (datos, seguridad, contratos compartidos, concurrencia, entrega) o no existe test que atrape una regresión: skill `adversarial-review` con **recibo**. El tamaño se decide por riesgo, no por número de archivos.
     1. Congelar el candidato: anotar en el plan el hash del diff y los archivos que lo componen, antes de que nadie lo lea.
     2. Profundidad por tier: pasivo → relectura estructural sin lentes; medio → una lente; alto → las 4R (Risk, Resilience, Readability, Reliability).
     3. Una única corrección acotada y un acuse final. Solo se corrige lo que confirme el `adversarial-verifier`.

3. **Auditoría del Harness**:
   - Ejecutar `aos doctor` (solo diagnóstico) si se tocaron skills, roles, hooks o el bloque gestionado. Nunca bloquea por sí mismo.

4. **Actualizar el Plan**:
   - Marcar la fase completada con `[x]` en el plan activo bajo `.aos/plans/active/`, con su evidencia (comandos, conteos, hallazgos).

5. **Capturar Aprendizajes**:
   - Trampa no obvia, bug sutil o caso borde → `.aos/knowledge/gotchas/<nombre>.md`.
   - Lección que guía la próxima tarea, con evidencia citada (comando o salida) → una fila en `.aos/knowledge/lessons/LEDGER.md`.

6. **Sincronizar Instrucciones**:
   - Si se actualizaron contratos, roles de agentes o reglas del proyecto, sincronizar instrucciones:
     ```bash
     aos sync
     ```

7. **Commit Atómico (solo si el usuario lo pide)**:
   - Realizar commit únicamente de los archivos específicos afectados por esta tarea. Nunca hacer `git add -A` a ciegas:
     ```bash
     python .aos/skills/bin/git_atomic_commit.py -m "tipo(alcance): descripcion clara" -f archivo1 archivo2
     ```
   - El hook `pre-commit` bloquea archivos que coincidan con `deny_paths` de `.aos/config.json` (secretos, claves).
