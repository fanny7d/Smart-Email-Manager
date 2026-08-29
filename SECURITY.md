# Security policy

## Supported versions

Until the first stable release, only the latest `main` revision and latest tagged beta receive fixes.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for this repository:

1. Open the repository's **Security** tab.
2. Choose **Advisories** → **Report a vulnerability**.
3. Include affected versions, impact, reproduction steps and any proposed mitigation.

Do not include live mailbox credentials, refresh tokens, API tokens, message content or personal data.
If a minimal reproduction needs secrets, use disposable credentials and revoke them immediately afterward.

We aim to acknowledge reports within 5 business days. Disclosure timing is coordinated after a fix and
release plan are ready. Please do not publicly disclose an unresolved issue before coordination.

## Security boundaries

- Microsoft credentials and forwarding/proxy secrets must remain encrypted at rest.
- API, share and project-claim tokens are write-only or hash-only and must never appear in logs.
- Production requires explicit API authentication and a user-supplied master key.
- Destructive mailbox actions require explicit user intent and must be scoped to exact resources.
- Browser and extension tokens remain session-scoped.

See [docs/architecture.md](docs/architecture.md) for the trust and process boundaries.
