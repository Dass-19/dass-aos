---
id: 202610031411
type: skill-spec
status: evergreen
cost: on-demand
name: "checkov-scan"
description: "Escanea IaC, contenedores y pipelines con Checkov; soporta --dry-run."
runtime: python
applies_when: ["*.tf", "*/*.tf", "*/*/*.tf", "*.bicep", "*/*.bicep", "Dockerfile", "*/Dockerfile", "*.Dockerfile", "Chart.yaml", "*/Chart.yaml", "*/*/Chart.yaml", "kustomization.yaml", "*/kustomization.yaml", "*/*/kustomization.yaml", "serverless.yml", "serverless.yaml", "cdk.json", "template.yaml", "k8s", "*/k8s", "manifests", "helm", "infra", "cloudformation", ".github/workflows/*.yml", ".github/workflows/*.yaml", ".gitlab-ci.yml", "azure-pipelines.yml", "bitbucket-pipelines.yml", ".circleci/config.yml", "ansible.cfg", "playbook*.yml"]
entrypoint: "aos scan --tool checkov"
inputs:
  - name: project_root
    type: string
    required: false
  - name: dry_run
    type: boolean
    required: false
outputs:
  format: "stdout | exit-code"
created: 2026-10-03
updated: 2026-10-05
---

# Skill: checkov-scan

> Escaneo de IaC / contenedores / pipelines con Checkov. Soporta `--dry-run`.

## Comando
```bash
aos scan --tool checkov [--dry-run]
# O con CLI instalado:
aos scan --tool checkov [--dry-run]
```
