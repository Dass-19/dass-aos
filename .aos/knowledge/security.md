# Security Standards (stack-agnostic)

> Status: evergreen · 2026-10-05

## 1. Authentication & Authorization
- Prefer short-lived credentials + refresh/rotation.
- Never store secrets in source, logs or client bundles.
- Privileged operations require both authentication and fine-grained authorization.

## 2. Secrets Management
- Environment variables or a secrets manager.
- `.env` (and equivalents) must never be committed.
- Rotate any exposed secret within 24 h.

## 3. Input Validation & Sanitization
- Validate every external input at the boundary.
- Prefer schema validation over ad-hoc checks.
- Escape output according to context.
- Never build queries, commands or markup via string concatenation.

## 4. Mandatory Scanners (with dry-run support)

### Semgrep (SAST)
- Command: `python aos.py scan --tool semgrep`
- Supports `--dry-run` (exits 0 and prints guidance when the tool is missing).
- Default packs: security-audit + OWASP-oriented rules.

### Checkov (IaC)
- Command: `python aos.py scan --tool checkov`
- Supports `--dry-run`.
- Applies to any infrastructure-as-code, containers, pipelines, etc.

### Dependency scanning
- Use the language-native or universal tool available in the project (osv-scanner, npm audit, pip-audit, etc.).
- Block known critical CVEs.

## 5. Logging & Observability
- Never log secrets, tokens or full PII.
- Security-relevant events should be emitted as domain events.

## 6. Secure Defaults
- Transport security everywhere.
- Security headers where applicable.
- Least privilege for all service identities.

## 7. When a new control is introduced
1. Document it here.
2. Ensure `aos scan` or `aos verify` validates it.
3. Add a gotcha if non-obvious.
4. Run `python aos.py sync`.
