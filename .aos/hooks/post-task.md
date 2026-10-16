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

2. **Verificación en Vivo y Revisión**:
   - Si se tocó UI, API, CLI o una app de escritorio: skill `live-verify` (levantar, ejercitar, mirar la evidencia y corregir, hasta 3 rondas).
   - Si se tocó más de un archivo: skill `adversarial-review`, con al menos la lente que más afecte. Solo se corrige lo que confirme el `adversarial-verifier`.

3. **Actualizar el Plan**:
   - Marcar la fase completada con `[x]` en el plan activo bajo `.aos/plans/active/`.

4. **Capturar Aprendizajes**:
   - Si se descubrió una trampa no obvia, bug sutil o caso borde, documentar un nuevo archivo en `.aos/knowledge/gotchas/<nombre>.md`.

5. **Sincronizar Instrucciones**:
   - Si se actualizaron contratos, roles de agentes o reglas del proyecto, sincronizar instrucciones:
     ```bash
     aos sync
     ```

6. **Commit Atómico (solo si el usuario lo pide)**:
   - Realizar commit únicamente de los archivos específicos afectados por esta tarea. Nunca hacer `git add -A` a ciegas:
     ```bash
     python .aos/skills/bin/git_atomic_commit.py -m "tipo(alcance): descripcion clara" -f archivo1 archivo2
     ```
