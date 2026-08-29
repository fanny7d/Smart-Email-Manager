# Contributing

Thank you for improving Smart Email Manager.

## Before opening a change

- Search existing issues and discussions.
- Keep the product Outlook-only unless a proposal is accepted first.
- Never include mailbox credentials, refresh tokens, API tokens, private emails or production data.
- Use disposable accounts and messages for provider acceptance.

## Development setup

```bash
createdb smart_email_manager_test
uv sync --all-groups --locked
uv run sem-migrate
pnpm install --frozen-lockfile
make verify
```

PostgreSQL 18, Python 3.12–3.14, Node.js 24 and pnpm 11 are supported.

## Pull requests

1. Create a focused branch and keep unrelated changes out.
2. Add or update tests for behavior changes.
3. Regenerate `contracts/openapi.json` and the generated TypeScript client when the API changes.
4. Add an `Unreleased` changelog entry for user-visible changes.
5. Run `make verify`. Run `make cli-acceptance` for CLI or automation changes.
6. Explain migration and rollback behavior for schema changes.

Pull requests must not weaken authentication, encryption, secret redaction, destructive confirmations,
bounded concurrency or durable job semantics without an explicit security review.

## Reporting security issues

Do not open a public issue for a vulnerability. Follow [SECURITY.md](SECURITY.md).
