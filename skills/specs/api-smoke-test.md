---
id: 202610031417
type: skill-spec
status: evergreen
name: "api-smoke-test"
runtime: python
entrypoint: "skills/bin/run_smoke_test.py"
inputs:
  - name: base_url
    type: string
    required: true
  - name: contract_path
    type: string
    required: false
outputs:
  format: "json | exit-code"
created: 2026-10-03
updated: 2026-10-05
---

# Skill: api-smoke-test

> Verifica endpoints críticos según los contratos HTTP declarados.

## Comando
```bash
python skills/bin/run_smoke_test.py --base_url "http://localhost:8000" --contract_path ".aos/contracts/http/example.yaml"
```
