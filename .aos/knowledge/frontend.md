# Frontend Standards (stack-agnostic)

> Customise concrete UI libraries and state solutions in project-specific notes.

## Core principles
- Prefer pure, predictable UI pieces; isolate side-effects.
- Accessibility is mandatory (semantic structure, keyboard, screen-reader support).
- No secrets or long-lived privileged tokens in client-side bundles.

## Contracts
- Consume only the HTTP contracts defined under `.aos/contracts/http/`.
- Prefer generated clients (see `python aos.py generate-client`) over hand-written API calls.

## Security on the client
- Sanitize any user-generated content before rendering.
- Apply the strongest practical content-security policy.
- Prefer secure, httpOnly storage mechanisms for credentials when the threat model includes XSS.
