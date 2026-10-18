# Production and security checklist

**Language:** English · [Русский](../production-operations.md) · [English index](README.md)

PrimaryKit ships examples and secure defaults; a detached client is **not production-certified** simply because the source repository's CI passed. Review the specific generated module composition and all client-owned domain rules.

## Before release

1. **Dependencies and tests:** use committed `uv.lock`, `uv sync --locked --all-groups`, Ruff, Django check / `check --deploy`, pytest and PostgreSQL integration tests for locking-sensitive code. Validate detached generation from a clean checkout.
2. **Migrations:** review, commit and apply **client-owned** migration files on staging first. Never run `makemigrations` on production; use planned expand/contract for incompatible schema changes.
3. **Auth and data isolation:** check owner/tenant authorization for list/detail/create/update/delete/custom actions, role changes, refresh sessions, object storage and chat; verify negative IDOR and cross-scope tests.
4. **Secrets and network:** unique Django secret, explicit allowed hosts, CSRF origins, HTTPS reverse proxy, trusted proxy headers only behind a proxy that overwrites them, no public PostgreSQL/Redis/RabbitMQ ports. Disable DEBUG.
5. **Operations:** external PostgreSQL backups and tested restores, separate object-storage backups, monitoring of live/ready health checks, structured logs, resource limits, alerts and rollback plans.
6. **External services:** configure SMTP before enabling email flows, private S3-compatible storage for scalable files, edge/shared rate limits, trusted webhook destinations and provider sandbox tests.
7. **Features:** enable optional Realtime, scheduler, retention processing, Redis and Celery deliberately. Review rate limits, quotas, legal obligations, polling load and retention jobs per deployed client.

## Mandatory module-specific caveats

- **Device sessions:** refresh/logout revocation is immediate but previously issued access tokens may remain valid until their expiry. Coordinate a re-login when rolling out sid-bound refresh tokens.
- **Realtime:** require WSS/TLS, an exact Origin allowlist, a trusted ASGI server and resource limits. Current PostgreSQL polling is not suitable for unlimited connections.
- **Tasks and Outbox:** require idempotent handlers, lease/recovery monitoring, retry budgets and reconciliation; at-least-once delivery is not exactly-once external effects.
- **Scheduler:** define timezone/DST semantics and run multiple schedulers only under verified PostgreSQL lease fencing. No implicit cron-like reliability without a running worker.
- **Quotas:** keep the authoritative counter and mutation in one PostgreSQL transaction; a quota alone is **not** permission to invoke a business command.
- **Privacy:** client handlers must preserve legally required financial records; back-ups, external services and audit logs need separate retention review. No auto-execution by default.
- **Payments:** do not accept money without a provider-specific, sandbox-tested signed webhook, verified settlement/reconciliation, refunds and audit.

## Public repository readiness

Making the **source repository** public is separate from deploying a backend. Before changing visibility, review *entire Git history* for credentials, private client data and redistribution rights; preserve the selected [MIT license](../../LICENSE); configure security reporting and enforce branch protection. **Policy files and a passing workflow do not enable protection by themselves.** See the [maintainer playbook](../maintainer-playbook.md).

See the full [source production runbook](../production-operations.md) and [project status](project-status.md).
