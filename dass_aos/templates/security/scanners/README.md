# Security Scanners

DASS-AOS integra escáneres de seguridad multiplataforma mediante el comando `aos scan`:
- **Semgrep** (SAST): Análisis estático de código fuente contra reglas de seguridad y auditoría OWASP.
- **Checkov** (IaC): Análisis de infraestructura como código, manifiestos y pipelines.

## Uso
```bash
# Ejecutar ambos escáneres en modo simulación (recomendado en local)
aos scan --dry-run

# Ejecutar un escáner específico
aos scan --tool semgrep
aos scan --tool checkov
```

Puedes colocar reglas personalizadas de Semgrep (`.yaml`) en este directorio y pasarlas con `--config`.
