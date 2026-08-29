# Outlook feature completion matrix

| Area | Status | Evidence / boundary |
|---|---|---|
| FastAPI, PostgreSQL 18, React and CLI | Done | one versioned `/api/v1` contract; persistent CLI config, secure token file and isolated E2E acceptance |
| Outlook account/import model | Done | API schemas and database constraints accept Outlook only |
| Graph and OAuth IMAP | Done | Graph adapter plus Outlook OAuth IMAP fallback; Graph consent remains optional |
| Verification-code center | Done | single/fleet API, CLI and React; Inbox/Junk, time window, bounded concurrency and partial errors |
| Fleet health and smart views | Done | independent lifecycle, authorization, token, mail and proxy status |
| Groups, tags, aliases and stable bulk scope | Done | three-level hierarchy, saved views and single-use bulk previews |
| Mail operations | Done | list, detail, raw MIME, attachments, mark-read and delete |
| Persistent automation | Done | PostgreSQL jobs, recovery, events, pause/resume/cancel and schedules |
| Token refresh | Done | Graph/IMAP refresh, rotation history and scheduled jobs |
| Proxy management | Done | encrypted inheritance/override and health probes; local port 7890 is the deployment target |
| SMTP forwarding | Done | encrypted destinations, cursor, dedupe, retry and jobs |
| Retention and read-only shares | Done | per-account cache policy, sync/prune, scoped expiry/revoke links |
| Project account leases | Done | durable claims, heartbeat, expiry recovery and event timeline |
| API tokens and encryption | Done | hashed scoped tokens and AES-GCM key rotation |
| React and browser extension | Done | shared generated API contract and session-only browser tokens |
| Open-source release baseline | Done | MIT license, community health files, CI/CodeQL, Dependabot, secret and dependency audits, verified wheel/sdist |
| Removed scope | Done | no generic password IMAP, temporary mail, Telegram, WeCom, WebDAV or legacy SQLite migration endpoints |

Real Outlook acceptance is recorded separately from mocked tests and synthetic scale evidence.
