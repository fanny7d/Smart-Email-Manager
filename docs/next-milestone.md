# Next milestone: operational rollout

The Outlook OAuth IMAP, local proxy and verification-code core have passed live acceptance. Graph is optional.

## Acceptance sequence

1. Import additional Outlook mailboxes in controlled batches and run post-import connectivity jobs.
2. Use groups and tags for ownership, purpose, region and proxy policy; use saved health views for daily triage.
3. Create scoped API tokens for each automation instead of sharing the bootstrap token.
4. Observe code-query latency and Microsoft throttling, then tune the bounded concurrency only from measured evidence.
5. Add Graph consent later only if Graph-specific throughput or capabilities are needed.

Graph consent can be added later for performance and richer Microsoft APIs; it is not required for Outlook OAuth IMAP operation.
