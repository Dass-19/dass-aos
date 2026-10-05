# Contracts Layer (stack-agnostic)

All public interfaces live here. Agents must never invent endpoints, events, or schemas that are not declared.

```
contracts/
├── events/     # Domain events (CloudEvents-style recommended)
├── http/       # OpenAPI 3.x fragments or full specs
└── schemas/    # Shared JSON Schema / equivalent
```

## Workflow
1. Write or update the contract **first**.
2. Run `python aos.py generate-client --contract <spec>` if consumers need typed clients.
3. Implement against the contract.
4. Verify with `python aos.py verify` and contract tests.
5. Breaking changes → new version + ADR when external consumers are affected.
