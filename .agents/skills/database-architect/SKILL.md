---
name: database-architect
description: Review or design PostgreSQL and Django ORM schemas, migrations, indexes, query plans, transactions, locks, soft deletion and data consistency. Use for any nontrivial database change or slow query.
---

# Database Architect for PrimaryKit

Use for Django models, constraints, SQL queries, migrations, warehouses/stock, wallets/payments, data integrity, performance, and scaling. Read `docs/core-conventions.md`.

## Procedure

1. List invariants, cardinalities, read/write ratios, isolation requirements, and lifecycle (retention, recovery, soft deletion).
2. Specify tables, foreign keys, nullability, uniqueness and check constraints. Put enforceable invariants in PostgreSQL, not only in serializers.
3. Compare storage alternatives (normal columns, JSONB, related attribute tables); justify with query patterns, schema change cost, and indexability.
4. Identify hot queries, access controls, indexes, sort/filter patterns and N+1 risks; request real `EXPLAIN (ANALYZE, BUFFERS)` from a safe staging clone with representative data when needed. **Do not execute ANALYZE on mutating statements on live data.**
5. Design transactions and concurrency controls: `atomic`, conditional UPDATE, `select_for_update`, lock order, retry on serialization/deadlock, unique idempotency keys.
6. Write migration plan: additive / backfill / switch / contract for existing clients. Include lock/scan estimates, constraint validation, rollback or forward-fix, data backups where relevant.
7. Verify with tests against PostgreSQL, including two competing writers when an invariant depends on concurrency. SQLite is not sufficient for lock behavior.
8. Record assumptions, alternatives, expected impact and evidence. Label unmeasured performance hypotheses.

## PrimaryKit-specific restrictions

- PrimaryKit's reusable catalog intentionally omits historical app migrations. Generated client repos **must commit every migration** and cannot delete migration history for updates.
- `SoftDeleteModel` is opt-in, not safe for every table. Default manager filters deleted rows; the unfiltered base manager preserves relationship resolution. Neither queryset nor instance soft deletion cascades or emits ordinary delete signals.
- Soft deletion does **not** release a database UNIQUE value. If reusing keys is required, design a PostgreSQL partial unique constraint (`condition=Q(deleted_at__isnull=True)`) deliberately and test restores.
- Bulk QuerySet `update()` bypasses `save()`, `auto_now` and Django save signals: don't rely on implicit timestamp updates.
- Wallet and stock ledgers use immutable movements plus bounded/atomic balance updates, never a naked read-add-save pattern.

## Deliverable

Return: table/constraint design; query/index matrix; transaction strategy; migration safety; tests; rollback; alternatives and open risks.

Read [PostgreSQL checklist](references/postgresql-checklist.md) when evaluating an implementation.
