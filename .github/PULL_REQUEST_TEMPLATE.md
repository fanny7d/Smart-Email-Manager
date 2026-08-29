# Pull request

## Summary

Describe the problem and the smallest change that solves it.

## Validation

- [ ] `make verify`
- [ ] Tests added or updated
- [ ] OpenAPI and generated client refreshed when applicable
- [ ] `CHANGELOG.md` updated for user-visible behavior
- [ ] `make cli-acceptance` run for CLI/automation changes

## Safety and compatibility

- [ ] No credentials, private mailbox data or generated local files are included
- [ ] Database migration and rollback behavior is documented
- [ ] Destructive actions remain explicitly confirmed and narrowly scoped
- [ ] Provider/network calls remain outside long database transactions
