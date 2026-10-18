# Durable usage quotas (#49)

**Language:** English · [Full reference (EN)](../usage-quotas.md) · [Docs index](README.md)

`apps/usage_quotas` is a **service-only** optional PostgreSQL module. It provisions explicitly scoped owner/tenant policies with half-open windows `[period_start, period_end)` and atomically consumes units with a durable event log.

## Trusted service workflow

The client provisions through privileged application code using `provision_quota(scope="owner"|"tenant", scope_id=..., code=..., period_start=..., period_end=..., limit_units=...)`. Clients query via `find_current_quota(actor=..., code=..., tenant_id=...)`, consume via `consume_usage(actor=..., policy_id=..., event_key=..., units=1)`, then read via `get_quota_status(...)`.

**The business command must authorize the underlying action separately** — belonging to an organization or possessing remaining quota is not itself a grant to do anything. Run consumption and the business mutation **in one transaction**. Reuse the same policy ID and event key on retries, including after period changes, to avoid double-counting.

PostgreSQL locking enforces atomic counts; quota provisioning rejects overlapping windows for the same scope/code. Immutable usage events retain the policy snapshot. Deleting event keys too early reopens the replay window. SQLite intentionally does not provide the production contract. Avoid Redis as the usage authority and plan for lock contention on very hot quota policies.

The module has no public provisioning endpoint, billing system, automatic renewals, chargebacks, refunds, or subscription entitlements.

```bash
uv run python scripts/new_project.py ../quota-api --name quota-api --apps usage_quotas
cd ../quota-api
uv run python manage.py makemigrations users usage_quotas
uv run python manage.py migrate
```

See [full source API and tests](../usage-quotas.md).
