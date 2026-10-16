# Hook de Pre-Tarea (Pre-Task)
> Obligatorio antes de iniciar cualquier modificación en el código.

1. **Verificar Inicio de Sesión**: Confirmar que `aos refresh` ya fue ejecutado.
2. **Selección Atómica de Tarea**: Tomar **únicamente** la siguiente tarea sin marcar `[ ]` en `.aos/plans/active/`. No agrupar múltiples fases a la vez.
3. **Inspeccionar Contratos**: Revisar `.aos/contracts/http/`, `.aos/contracts/events/` y `.aos/contracts/schemas/` para verificar que cualquier endpoint, evento o tipo de dato a modificar ya esté formalmente declarado.
4. **Consultar Codebase Memory**: Utilizar `search_graph` o `query_graph` para inspeccionar usos entre módulos y dependencias cruzadas. Nunca asumir estructuras de archivos sin verificar.
5. **Comprobar Estado Real de Archivos**: Emplear herramientas de lectura del filesystem para confirmar el contenido real antes de hacer ediciones.
6. **Asumir Rol**: Declarar explícitamente qué rol de agente se está asumiendo para esta fase (`app-builder`, `refactorer`, `reviewer`, `security-auditor`, `architect`, `qa-tester`, `adversarial-verifier`).
7. **Línea Base**: Antes de tocar nada, ejecutar `aos verify` y los gates del proyecto y anotar lo que ya falla, para no confundirlo con una regresión.
8. **Elegir el Flujo**: Si el cambio cruza capas o toca más de tres archivos, seguir la skill `phased-delivery`.
