# Architecture decisions

## Status

Implemented API-first platform baseline; real external-service acceptance remains tracked separately.

## Process boundaries

- `sem-api`: HTTP validation, authentication, short database transactions, and job creation.
- `sem-worker`: leases persistent job items and performs provider/network work outside database transactions.
- `sem`: CLI client using HTTP only.
- `web`: React client using the generated OpenAPI boundary.
- `extension`: Manifest V3 client importing the same generated v1 SDK.

The API, worker, and CLI may ship from the same Python distribution, but their imports and runtime responsibilities remain separate.

## Contract policy

- Version all public endpoints below `/api/v1`.
- Give every operation a stable explicit `operation_id`.
- Commit `contracts/openapi.json` and fail CI when generation produces an unreviewed diff.
- Use typed problem responses for errors.
- Return `202 Accepted` plus a Job resource for long-running operations.
- Support `Idempotency-Key` on automation-facing create operations.
- Prefer cursor pagination and stable sort keys over very large offsets.

## Database policy

- PostgreSQL 18 is the only runtime database.
- Use UUIDv7 public identifiers.
- Store all timestamps as `timestamptz`.
- Keep account secrets in a separate table and never serialize ORM objects directly to API responses.
- Keep lifecycle, authorization, token, mail health, proxy health, and job status independent.
- Use short transactions; never hold a transaction open while calling Graph, Outlook IMAP, proxies, or SMTP.
- Alembic migrations are reviewed artifacts, not blindly applied autogenerate output.
- Published migration revisions are immutable. Early revisions contain subsequently removed provider
  tables; revision `0d4e5f6a7b8c` removes them. They remain in the chain so deployed databases can upgrade
  safely and must not be deleted merely to make a fresh schema history look shorter.

## Job policy

- `jobs`, `job_items`, and `job_events` are the source of truth.
- Workers lease items with `FOR UPDATE SKIP LOCKED`.
- Leases expire and can be safely recovered after a process restart.
- Every external side effect requires an idempotency strategy.
- Jobs can pause before the next lease; project work uses separate hash-token leases with heartbeat and expiry recovery.
- `LISTEN/NOTIFY` may wake workers later, but polling remains the durable fallback.
- SSE reads persistent events; browser disconnection does not cancel a job.

## Client policy

- React and CLI never connect directly to PostgreSQL.
- CLI writes machine-readable results to stdout and progress to stderr.
- Automation supports stable JSON/JSONL output and non-interactive authentication.
- Browser and extension tokens live in session storage; persistent service tokens remain scoped and revocable.

## Provider policy

- Outlook is the only account type and provider accepted by the API and database constraints.
- Graph is preferred when delegated permissions are available; OAuth IMAP is the fallback and requires no Gmail account.
- Verification-code reads cover Inbox and Junk Email, stay read-only, and never log codes or OAuth credentials.
- Bulk verification-code reads use bounded concurrency so one automation run cannot create an unbounded Microsoft connection burst.
