# PostgreSQL review checklist

1. Models: explicit indexes for filter+sort, foreign keys, constraints, `on_delete` and tenant scoping.
2. Unique + nullable: document NULL semantics, functional/case-insensitive values, soft-delete partial uniqueness.
3. Query: `EXPLAIN (ANALYZE, BUFFERS)` on staging for SELECT; review estimated vs actual rows, scans, joins, sort memory, shared buffers, query frequency.
4. ORM: `select_related`, `prefetch_related`, avoid per-item counts/queries; verify with query count tests.
5. Concurrency: lost updates, deadlocks, lock ordering, retries, race-resistant state transitions, idempotency.
6. Migrations: lock level, index creation strategy, constraint validation, backfill batching, production compatibility and rollback.
7. Operations: pool limits, connection storms, autovacuum, bloat, backup/restore and connection timeouts.
8. Never create indexes without considering write overhead and maintenance.

References:
- https://www.postgresql.org/docs/current/using-explain.html
- https://www.postgresql.org/docs/current/explicit-locking.html
- https://docs.djangoproject.com/en/6.1/topics/db/transactions/
- https://docs.djangoproject.com/en/6.1/ref/models/constraints/
- https://github.com/supabase/agent-skills/tree/main/skills/supabase-postgres-best-practices

External skills are reading material; review their source and license before installing or executing anything.
