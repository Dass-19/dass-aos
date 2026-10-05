# Backend Standards (stack-agnostic)

> Customise the concrete stack in the project’s own notes after bootstrap. This file stays technology-neutral.

## Mandatory practices
1. Every public endpoint must have a corresponding contract under `.aos/contracts/http/`.
2. Domain events must be defined under `.aos/contracts/events/` before being emitted.
3. Schema/data migrations are atomic and reversible; use `python aos.py verify --type migration`.
4. Business logic lives behind clear interfaces (use-cases / services), never mixed with transport or persistence details.
5. All external I/O is behind interfaces so it can be substituted in tests.

## Error handling
- Map domain errors to stable status codes / error codes.
- Never leak internal details to external callers in production.

## Testing
- Unit tests for pure domain logic.
- Integration tests for adapters.
- Smoke tests and contract verification via `python aos.py verify` after any public surface change.
