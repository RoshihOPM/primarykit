# Privacy retention and legal holds (#51)

**Language:** English · [Русский](../privacy-retention.md) · [Docs index](README.md)

`apps/privacy` is an **opt-in client-directed retention coordinator** supporting `redact`, `anonymize`, and `delete` requests, dry-run, grace periods, legal holds, idempotency and audit. It requires `audit` and `tasks`. It does **not** implement generic cascading deletion or infer regulatory retention rules.

## Client policy contract

In **trusted client settings**, define `PRIVACY_RETENTION_POLICIES` per subject kind/code: allowed actions, a grace interval (0–3650 days), and an allowlisted `handler` import path such as `apps.customers.privacy.redact_customer`. The handler is called with `scope, kind, subject_id, action`; it must operate on the client's own authorized records, preserve required financial evidence, be idempotent and keep DB mutations transactional.

The service offers `preview`, `request_retention`, `execute_manually`, `set_legal_hold`, `release_legal_hold`, `cancel_request`. Admin commands require an active superuser **inside the service**. There is **no public HTTP endpoint**. Callers must additionally enforce their client business and access rules.

Dry-run never changes DB state. `request_retention` stores a pending request. Legal hold prevents execution; relevant transitions generate Audit records without old/new PII values. A policy fingerprint is revalidated before work so changed policy/handler definitions cannot silently execute previous requests. Competing commands use PostgreSQL locks; retry delivery from Tasks is at least once.

## Enabling background execution

`PRIVACY_AUTO_EXECUTION_ENABLED=False` is the default. After a legal/security review and tested client handler, explicitly enable it for **new** requests and run the `run_background_jobs` worker. Turning it on does not retroactively process old pending manual requests. Turning it off causes previously queued auto jobs to refuse execution and may lead to retries/failed tasks.

```bash
uv run python scripts/new_project.py ../privacy-api --name privacy-api --apps privacy
cd ../privacy-api
uv run python manage.py makemigrations users audit tasks privacy
uv run python manage.py migrate
```

Side effects such as third-party API calls, mail or S3 deletion must use separate durable, idempotent workflows. Backups, logs, archives and mandatory record retention require their own legal policies. Executed anonymization should not be assumed reversible.

[Detailed source reference (RU)](../privacy-retention.md).
