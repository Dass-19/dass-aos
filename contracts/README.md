# Capa de Contratos (Stack-Agnostic)

Todas las interfaces públicas del sistema residen aquí. Los agentes nunca deben inventar endpoints, eventos o esquemas que no estén previamente declarados.

```
contracts/
├── events/     # Eventos de dominio (recomendado formato estilo CloudEvents)
├── http/       # Fragmentos o especificaciones completas de OpenAPI 3.x
└── schemas/    # Esquemas compartidos (JSON Schema o equivalente)
```

## Flujo de Trabajo (Contract-First)
1. Escribir o actualizar el contrato **primero**.
2. Ejecutar `python aos.py generate-client --contract <spec>` si los consumidores requieren clientes tipados.
3. Implementar el código contra el contrato establecido.
4. Validar mediante `python aos.py verify` y pruebas de contrato.
5. Cambios que rompen compatibilidad (*Breaking Changes*) → nueva versión del contrato y registro de un ADR si afecta a consumidores externos.
