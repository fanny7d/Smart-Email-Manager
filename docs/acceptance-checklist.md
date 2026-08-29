# Outlook acceptance checklist

Use a disposable message and never paste Outlook credentials into shell history.

```bash
sem health check --account-id ACCOUNT_ID --mode connectivity
sem mail list ACCOUNT_ID --method auto --folder all
sem codes latest ACCOUNT_ID --recent-minutes 30
sem codes query --account-id ACCOUNT_ID --recent-minutes 30
sem proxies probe PROFILE_ID
```

Required evidence:

- OAuth IMAP or Graph reports a healthy Outlook connection through the configured proxy.
- A known 4–8 digit or context-bound alphanumeric verification code is returned with account, sender, subject, folder, timestamp and provider method.
- Inbox and Junk Email are searched; querying does not mark the message read or delete it.
- A fleet query isolates failed accounts in `partial_errors` instead of discarding successful results.
- Raw MIME, attachment, mark-read and delete are exercised only on disposable messages.
- `pytest`, Ruff, mypy, React tests/build, extension build, OpenAPI generation, migration check, scale gate and Compose validation pass.
