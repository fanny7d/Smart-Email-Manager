# 10,000-account scale acceptance

Run the repeatable gate with:

```bash
make scale-check
```

The benchmark refuses databases whose names do not end in `_test`. It inserts all synthetic rows
inside one PostgreSQL transaction, exercises the fleet summary, stable cursor pagination and a
failure smart view, then rolls the transaction back.

## 2026-08-29 local PostgreSQL 18 result

| Check | Result |
|---|---:|
| Synthetic accounts | 10,000 |
| Fleet summary | 0.0391 s |
| First 100-row cursor page | 0.0222 s |
| Failure smart-view page | 0.0051 s |
| Next cursor | present |
| Maximum account rows supplied to the React table per page | 100 |
| Persistent test data | none; transaction rolled back |

The timings are local evidence, not a universal service-level objective. The invariant enforced by
the gate is that the API and React client retain a bounded page while summary and smart-view queries
operate entirely in PostgreSQL without remote provider calls.
