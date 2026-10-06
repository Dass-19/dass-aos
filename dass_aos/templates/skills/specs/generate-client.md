---
id: 202610031412
type: skill-spec
status: evergreen
name: "generate-client"
description: "Genera clientes tipados a partir de los contratos OpenAPI de .aos/contracts/http/."
runtime: python
applies_when: [".aos/contracts/http/*"]
entrypoint: "aos generate-client"
inputs:
  - name: contract
    type: string
    description: "Path to OpenAPI spec (YAML or JSON)"
    required: true
  - name: output
    type: string
    description: "Destination directory"
    required: true
  - name: generator
    type: string
    description: "generic | openapi-typescript | openapi-generator | datamodel-codegen"
    required: false
  - name: language
    type: string
    description: "Only used with openapi-generator (typescript-fetch, python, go, etc.)"
    required: false
outputs:
  format: "stdout | exit-code"
created: 2026-10-03
updated: 2026-10-05
---

# Skill: generate-client

> Genera clientes tipados a partir de contratos OpenAPI.  
> Stack-agnóstico con soporte para TypeScript, Python, Go, Java, o stubs documentados.

## Generadores soportados
- `openapi-typescript` → TypeScript types (`schema.d.ts`) + client stub
- `datamodel-codegen` → Python (modelos Pydantic)
- `openapi-generator` → Multi-lenguaje (`typescript-fetch`, `python`, `go`, etc.)
- `generic` → Valida presencia del contrato y emite README con instrucciones

## Comando
```bash
aos generate-client \
  --contract ".aos/contracts/http/example.yaml" \
  --output "./src/api/generated" \
  --generator openapi-typescript
```

## Cuándo usar
Inmediatamente después de crear o modificar cualquier contrato HTTP, antes de escribir código manual.
