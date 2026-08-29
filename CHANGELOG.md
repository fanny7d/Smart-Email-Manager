# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and releases use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Outlook-only API, CLI, React console and browser extension.
- Microsoft Graph integration with OAuth IMAP fallback.
- Single-account and fleet verification-code extraction.
- PostgreSQL-backed jobs, schedules, project leases, retention and sharing.
- Secure CLI configuration with a separate mode-`0600` token file.

### Security

- AES-GCM secret storage with versioned key rotation.
- Scoped, hash-only API tokens and lease/share tokens.
- Non-root, read-only production containers and least-privilege database roles.

## [0.1.0] - 2026-08-29

### Added

- Initial public beta baseline.
- Verified wheel and source distributions with published SHA-256 checksums.

[Unreleased]: https://github.com/fanny7d/Smart-Email-Manager/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/fanny7d/Smart-Email-Manager/releases/tag/v0.1.0
