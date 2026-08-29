# Production deployment

The production stack separates PostgreSQL bootstrap, migration and runtime roles:

- `sem_bootstrap` exists only for first-start database initialization.
- `sem_migrator` owns the database schema and runs Alembic.
- `sem_app` can read and mutate application rows but cannot run DDL.

PostgreSQL 18 stores versioned clusters below `/var/lib/postgresql`; the Compose volume intentionally mounts that parent directory so future `pg_upgrade --link` operations do not cross a mount boundary.

## Start

1. Copy `.env.production.example` to `.env.production` and replace every secret. Production startup
   rejects example placeholders, API tokens shorter than 32 characters and invalid master keys.
2. Keep the bind address on `127.0.0.1` unless a TLS reverse proxy protects the service.
3. Start and wait for every health gate:

   ```bash
   docker compose --env-file .env.production up -d --build
   docker compose --env-file .env.production ps
   curl -fsS http://127.0.0.1:8080/api/v1/system/health
   ```

4. Create a persistent scoped API token, move browsers and automation to it, then retire the bootstrap token.
5. Configure the encrypted Outlook proxy profile and run a disposable verification-code acceptance message.

Generate independent values without placing them in shell history:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
python -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
```

The first value is suitable for `SEM_API_TOKEN`; the second is the 32-byte `SEM_MASTER_KEY`. Store
production values in a secret manager or mounted files rather than committing `.env.production`.

For Docker/Kubernetes or an external secret manager, mount values as files and set `SEM_API_TOKEN_FILE`, `SEM_MASTER_KEY_FILE` and optionally `SEM_DATABASE_URL_FILE`. File values take precedence over their direct environment counterparts and empty/unreadable files fail startup.

## Upgrade and rollback

Before an upgrade, record image digests and take a PostgreSQL volume snapshot. Run `migrate` before API and Worker. Roll back application images only when the database migration is backward-compatible; otherwise restore the matching database snapshot.

## Acceptance gates

- API, Worker, Web and PostgreSQL report healthy.
- `alembic current` is the repository head.
- Runtime `sem_app` cannot create or alter tables.
- A synthetic account can be imported, health-checked, archived and purged.
- At least one real Outlook account passes OAuth IMAP or Graph mail list/detail.
- The configured Outlook proxy and SMTP destination pass real endpoint tests.
- A disposable Outlook verification message is found through both single-account and fleet code APIs.
- `make security-audit` and the repository secret scan report no known vulnerable dependencies or credentials.
