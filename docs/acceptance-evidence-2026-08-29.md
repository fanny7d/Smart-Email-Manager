# Acceptance evidence — 2026-08-29

This record separates implementation gates from credentialed external-service acceptance. No
credential values, mailbox addresses or one-time tokens are recorded here.

## Green implementation gates

- 71 backend tests and 2 focused frontend client tests passed after the Outlook-only, CLI and
  open-source hardening work on Python 3.12 and 3.14.
- Ruff and mypy passed across 92 Python source files.
- OpenAPI snapshot regenerated; React and Manifest V3 generated clients built from it.
- Alembic reported no model drift at revision `0d4e5f6a7b8c`.
- React production build and browser-extension production build passed.
- The transactional 10,000-account PostgreSQL 18 scale gate passed and rolled back all rows.
- The isolated CLI acceptance gate passed configuration/token permissions, create/read/update,
  stable bulk previews, proxy, retention, shares, SMTP, schedules, project leases, pause/resume/cancel,
  import commit/rollback and guarded cleanup; its `_test` database and temporary files were removed.
- Python and JavaScript dependency audits reported no known vulnerabilities after upgrading
  `cryptography`, `pytest`, the OpenAPI generator and the patched `js-yaml` resolution.
- The repository credential-pattern scan passed all publishable files; package metadata and Markdown
  checks passed; wheel and source distributions passed `twine check`.
- The installed wheel's `sem-migrate` entrypoint created a fresh PostgreSQL schema at revision
  `0d4e5f6a7b8c`, proving migration resources are included in the distribution.

## Browser extension

- Loaded `extension/dist` unpacked in Chrome for Testing 152 with an isolated profile.
- The popup connected to the local API and rendered fleet totals plus two account rows.
- A synthetic marker stored in `chrome.storage.session` was present during the browser session.
- After a full browser restart with the same profile, the session token length was zero while the
  local API URL remained in `chrome.storage.local`.
- Both temporary Chrome profiles were moved to Trash after acceptance.

## Production Compose

- The first current-image attempt exposed a production bug: empty `SEM_*_FILE` variables were
  parsed as a directory and stopped the migration container.
- Blank file-mount values now normalize to unset and have a regression test.
- Rebuilt API and Web images started in an isolated Compose project.
- PostgreSQL, API, Worker and Web started successfully; health-checked services were healthy.
- Migration head was `0d4e5f6a7b8c` in a newly rebuilt isolated production Compose stack.
- The `sem_app` runtime role was denied `CREATE TABLE`.
- A synthetic account completed create, metadata-health job, archive and guarded purge.
- Acceptance containers, network and PostgreSQL volume were removed afterward.

## Real Outlook account

- Import, encrypted secret storage, OAuth token exchange and initial IMAP inbox selection passed.
- The mailbox reported zero messages, so list success did not prove detail, MIME, attachment or
  mutation behavior against a real message.
- Microsoft Graph token exchange returned `AADSTS90023` because the supplied grant has no Graph
  permissions; automatic mail access correctly preferred IMAP.
- A later attempt to append a disposable acceptance message failed before APPEND with `User is
  authenticated but not connected`; no message was created or deleted.
- The provider now classifies this as retryable `IMAP_SESSION_NOT_CONNECTED` instead of a generic
  list failure.
- A subsequent connectivity job recovered to `IMAP_OK`. Mixed optional-fallback failures no longer
  invalidate a working authorization unless every provider attempt is a credential/Token error.
- A short disposable Outlook message with one attachment then passed list, detail, raw MIME,
  attachment download, mark-read, read-back and delete through automatic OAuth IMAP selection.
- A final list returned zero messages, proving the synthetic message was removed.
- A new disposable message containing code `738264` was found by the verification-code API and
  React page through OAuth IMAP via `socks5://127.0.0.1:7890`. The message remained unread before
  and after extraction, was then deleted, and a follow-up list confirmed it was absent.
- A second disposable Outlook message containing code `842731` and one attachment passed the CLI
  path for code extraction, list, detail, raw MIME download, attachment download, mark-read/read-back
  and guarded delete. The downloaded temporary files and remote synthetic message were removed.

## Supporting protocol services

- Proxy: an authenticated SOCKS5 service was configured as fallback behind an unreachable primary.
  The probe failed primary, reached Microsoft OIDC through fallback and returned
  `PROXY_FALLBACK_OK` without exposing credentials. The profile and container were removed.
- SMTP forwarding: an encrypted destination returned `SMTP_SENT`; the recipient GreenMail inbox
  contained the expected test subject. The destination and container were removed.

The earlier generic-password IMAP, chat notification, temporary-mail, WebDAV and legacy SQLite
experiments are no longer product acceptance evidence because the user removed those areas from scope.

## Outlook-only refactor

- API schemas and PostgreSQL checks now accept Outlook accounts only.
- Verification-code extraction is first-class across API, CLI and React, with bounded fleet concurrency,
  Inbox/Junk coverage, time windows and per-account partial errors.
- The product no longer exposes temporary mail, Telegram, WeCom, WebDAV or legacy SQLite migration routes.
- SMTP remains the sole forwarding channel. Graph remains optional; Outlook OAuth IMAP is the fallback.

## Optional future acceptance

- A consented Graph account can be accepted later for Graph-specific performance and message operations,
  but it is not required for the accepted Outlook OAuth IMAP workflow.
