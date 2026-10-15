# Audit Log v0.1

## Objective

Provide a **read-only application log of explicitly recorded business changes** for incident investigation and administrative accountability, without duplicating domain models. This is an app-level event table, not an immutable cryptographically protected compliance ledger.

## Schema and indexes

`AuditEvent` contains UUID, `occurred_at` UTC, optional FK actor, action code, `target_type`, `target_id` (string), and a bounded sanitized `changes` JSON snapshot. Never store raw request bodies, password hashes, tokens, secrets, credentials, mail links, or full PII.

Indexes: `occurred_at` (pagination), `(action, -occurred_at)`, `(target_type, target_id, -occurred_at)`.

`actor` is `SET_NULL` after deletion; no implicit user-PII snapshot. Projects with non-deletable compliance actor identifiers should model retention policy explicitly.

## Transaction rule

`record_audit_event(actor=..., action=..., target_type=..., target_id=..., changes=...)` from `apps.core.audit` is the dependency-safe entry point. It is a no-op if the Audit app was not selected for the generated project. When installed, it raises on storage failure, and the caller **must** make the business mutation and log insertion inside the **same** `transaction.atomic()` block. This guarantees rollback together. `on_commit` would not provide this guarantee for critical audit events.

Audit does not rely on model signals, because `QuerySet.update`/`bulk_update` bypass `save()` and save signals. Audit is explicit in Users and RBAC write actions. More applications should do likewise.

## Security

- Admin API: `GET /api/v1/admin/audit/events/` and `GET .../{uuid}/` with filters `action`, `target_type`, `target_id`, `actor`, `from`, `to`. Only active superusers. No write endpoints.
- Django Admin is read-only for active superusers.
- Model save/delete and QuerySet update/delete/bulk_update reject mutations, but direct SQL and database superusers **can still alter rows**. For tamper-evidence, use restricted DB permissions, append-only triggers and/or independent remote WORM storage, with backup/restore policy and retention laws.
- `changes` only accepts bounded JSON-safe values, blocks common credential-key names. This is defense in depth and **cannot guarantee no sensitive PII in arbitrary values**. Callers must explicitly pass safe business fields; no arbitrary model serialization.
- Targets are labels/IDs to avoid cascading deletes. No per-tenant list API; superuser access only. Multi-tenancy needs tenant scoping, partitions/retention policy and an explicit scoped admin role.
- Security-sensitive admin changes should not be editable through normal API; rollback audit logs and business changes together.

## Migration policy

New generated project: `makemigrations users audit` then `migrate`, commit both app migrations. Existing projects must generate and review new `audit` migration and backfill any desired historical audit events separately (never invent historical facts).

## Limitations

- Request correlation ID, login failure metrics, middleware automatic capture, async event ingestion, compliance retention and auditing every possible mutation are not implemented in v0.1.
- Event recording deliberately performs a DB insert on the critical path; benchmark with real project load.
