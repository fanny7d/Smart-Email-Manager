# CLI configuration and automation

`sem` is an HTTP-only client for `/api/v1`; it never connects directly to PostgreSQL.

## Configuration

The default file is `~/.config/smart-email-manager/config.toml`. Create and validate it with:

```bash
sem config init --api-url http://127.0.0.1:8000 --timeout 60
sem config show
sem config validate
```

The file stores connection settings only:

```toml
[client]
api_url = "http://127.0.0.1:8000"
timeout_seconds = 60
token_file = "/Users/you/.config/smart-email-manager/token"
```

Do not put a plaintext token in TOML. Configure it through a hidden prompt:

```bash
sem config token-set
```

The token is stored separately with mode `0600`. The CLI refuses group/world-readable, oversized,
empty or non-user-owned token files. In local development, the token may remain absent while the API
uses its localhost development bootstrap. Production requires a scoped token.

Configuration priority is:

1. root options such as `--config`, `--api-url`, `--token-file` and `--timeout`;
2. `SEM_API_URL`, `SEM_TOKEN`, `SEM_TOKEN_FILE`, `SEM_HTTP_TIMEOUT` and `SEM_CA_BUNDLE`;
3. `config.toml`;
4. localhost defaults.

Use `SEM_CONFIG_FILE` or the root `--config` option for multiple environments:

```bash
sem --config ~/.config/smart-email-manager/production.toml fleet summary
```

## Verification-code automation

```bash
sem codes latest ACCOUNT_ID --recent-minutes 30 --output json
sem codes query --account-id ACCOUNT_ID --recent-minutes 30 --output json
```

An empty `--account-id` selection queries active Outlook accounts up to `--account-limit`. Failed
mailboxes are isolated in `partial_errors` and do not discard successful results.

## Command coverage

The CLI covers account secrets, groups/tags/aliases, stable bulk previews, imports, live mail,
verification codes, proxies, token refresh, retained mail, shares, SMTP forwarding, schedules,
persistent jobs, work-project leases, audit history and key-rotation inventory. Destructive commands
require `--yes` or an interactive confirmation.

Run the isolated create/read/update/job/delete acceptance suite with:

```bash
make cli-acceptance
```

The suite creates a dedicated `_test` database, a temporary API/config/token, runs the command
workflows, and removes all temporary state afterward. It expects the local SOCKS5 proxy on port 7890.

Exit codes are `0` for success, `2` for arguments/configuration, and `3` for API or network errors.
