# Hook de Inicio de Sesión (Session-Start)
> Obligatorio al inicio de cada sesión con un agente de IA.

1. **Refresco de Memoria y Trampas Recientes**  
   Ejecutar el comando de refresco del CLI:
   ```bash
   aos refresh --gotchas-limit 5
   ```
   Esto expondrá:
   - Los gotchas más recientes documentados en `.aos/knowledge/gotchas/`.
   - El estado de la base de datos de grafo de `codebase-memory`.
   - El plan activo y la siguiente tarea pendiente.

2. **Cargar Contexto Global**  
   Consultar `.aos/config.json`, `.aos/knowledge/` y `.aos/decisions/` para calibrar las normas del proyecto.

3. **Identificar la Siguiente Tarea**  
   Localizar el plan activo en `.aos/plans/active/` e identificar el primer elemento sin marcar `[ ]`. No comenzar a escribir código todavía.

4. **Declarar Estado de Preparación**  
   Declarar brevemente que el contexto de la sesión está cargado, reconociendo las trampas recientes e indicando qué tarea del plan se va a abordar.
