# Usage Quotas — durable owner/tenant usage limits

`usage_quotas` is an **opt-in source-copy module**, not a billing system.
It requires Users and PostgreSQL. Organizations and Statistics are optional.
It offers *service APIs only*: there is no publicly writable endpoint, payment
integration, entitlement decision, automatic renewal, refund, reset, or external
billing-period inference. **Client code must provision quotas deliberately**,
after verifying its own product, billing, trial, or admin entitlement rules.

## Contract

- `provision_quota(scope="owner"|"tenant", scope_id=..., code=...,
  period_start=aware_dt, period_end=aware_dt, limit_units=..., expires_at=None,
  metadata=None)`: a trusted, privileged server operation. Tenant provisioning
  requires installed Organizations and an active organization; personal provisioning
  requires an active user. Configuration is not exposed over HTTP.
- `find_current_quota(actor=authenticated_user, code="api_calls",
  tenant_id=None)`: resolve *one* nonexpired window. Requires owner identity or
  active organization membership. Missing or ambiguous policies fail closed.
- `consume_usage(actor=authenticated_user, policy_id=policy.id,
  event_key="stable-business-action-id", units=1)`: compare-and-increment under
  a PostgreSQL transaction and create one immutable event with a policy snapshot.
  Returns `UsageResult(policy_id, code, used_units, limit_units, remaining_units,
  replayed)`. Pass **the same policy_id and key on retries**, including after
  period rollover; keys are unique *per policy*, not globally.
- `get_quota_status(actor=..., policy_id=...)`: scoped read of current counters.
  Optional Statistics exposes `usage_quotas.active_policies` (snapshot) and
  `usage_quotas.consumed_units` (period, filtered by event creation time).

Periods are explicit half-open intervals `[period_start, period_end)`; expiry
is also exclusive. A zero limit is a deliberately disabled policy. Periods for
the same scope and code cannot overlap via provisioning (PostgreSQL advisory lock
serializes writers). Adjacent windows are permitted. Policies are **immutable**:
replace changes through future non-overlapping policies, not direct row updates.
Usage event snapshots store the original cap, scope, window, and client metadata.
No Redis cache is an authority for usage or paid entitlements.

## Security, consistency and operations

Scope validation is done in the service, not just an HTTP queryset. Cross-user,
cross-tenant, inactive membership, anonymous and global superuser access all fail
closed with 404. A tenant policy is not accessible without Organizations. Any
member of an active organization may consume its quota; **clients must add their
own role/action authorization BEFORE calling consume_usage**. Quota ownership
does not grant permissions to perform the underlying business action.

Consume **inside the same database transaction** as the protected business
mutation; throw before performing work on `QuotaExceeded`. If the business
mutation fails, the usage event and counter roll back as well. For workflows with
external side effects use Outbox and a durable, application-defined business
idempotency key. Never publish effects before commit. PostgreSQL is mandatory for
provisioning/consumption; SQLite intentionally raises `NotSupportedError`.
Raw updates of policies or counters bypass guarantees and are unsupported.
Run PostgreSQL with ordinary READ COMMITTED; do not use a read replica for
authorization, provisioning, or consumption.

Events are a durable idempotency record: **deleting or pruning events early allows
old requests to be billed again**. Retention, reconciliation, historical storage
and GDPR policies belong to the client; retain event keys for the full expected
retry horizon. Avoid PII, secrets and provider tokens in quota codes, keys, or
policy metadata. Maintain separate entitlement approvals; usage metrics are not
invoices and do not prove payment.

The PostgreSQL row lock and conditional `UPDATE ... SET used_units=used_units+n`
serialize expensive same-quota writes. A very hot policy will become a lock
contention point: shard the *business* quota contract only with a reviewed design,
not by moving the authoritative count to Redis. No automatic negative/decrement
operation is provided because refunds require a separate audited policy.

## Generated-project setup

```bash
uv run python scripts/new_project.py ../quota-api --name quota-api --apps usage_quotas
cd ../quota-api
uv run python manage.py makemigrations users usage_quotas
uv run python manage.py migrate
uv run python -m apps.core.doctor --strict
uv run pytest
```

Commit the client's own migrations and run PostgreSQL integration/race tests
before production. An organization-scoped project opts into
`--apps organizations usage_quotas statistics`; no dependency on the original
PrimaryKit source is retained.
