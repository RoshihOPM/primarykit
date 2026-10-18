# PostgreSQL recurring scheduler (#47)

**Language:** English · [Русский](../tasks-architecture.md#повторяющиеся-расписания--postgresql-scheduler) · [Docs index](README.md)

Recurring schedules are part of `apps/tasks`, not a second queue. A `JobSchedule` selects trusted registered background handlers, and the existing `BackgroundJob` table/worker executes jobs at least once. There is **no mandatory Redis, Celery or RabbitMQ**.

## Configure trusted recurring jobs

Inside an explicit client deployment command (not `AppConfig.ready()`), define a stable name and namespace, a handler `code` already listed in `BACKGROUND_JOB_HANDLERS`, an IANA timezone, local hour/minute, optional weekdays, bounded attempts and payload:

```python
from datetime import datetime, timezone
from apps.tasks.scheduler import register_schedule

register_schedule(
    name="nightly-report",
    code="reports.generate",
    payload={"report": "summary"},
    namespace="default",
    timezone_name="Asia/Almaty",
    hour=2,
    minute=30,
    weekdays=[0, 1, 2, 3, 4],
    max_attempts=5,
    start_at=datetime.now(timezone.utc),
)
```

A second registration of the **same** configuration is idempotent and does not reset the cursor; a changed definition with the same name is rejected until the client deliberately reviews/migrates it.

## Deployment processes

After generating and committing your client migration for `tasks`, run the dispatcher and worker as separate processes:

```bash
uv run python manage.py run_schedule_dispatcher --batch-size 100 --poll-seconds 10
uv run python manage.py run_background_jobs --lease-seconds 900
```

Use `run_schedule_dispatcher --once` for diagnostics. PostgreSQL advisory transaction locks coordinate concurrent dispatchers; `SELECT FOR UPDATE SKIP LOCKED` prevents duplicate scheduling; job insert and cursor update commit atomically. Jobs use stable idempotency keys derived from schedule identity and UTC scheduled time. Fencing prevents an expired worker token from marking a reclaimed task finished, **not** from duplicating an external request.

## Timing and failure semantics

Local wall-clock schedules use an IANA zone. Missing times in spring DST are skipped; fall fold chooses the first occurrence. A long outage is **coalesced** to one oldest missed firing, not backfilled for every missed interval. No generic cron syntax, exactly-once external effects, automatic long-job heartbeat or UI is included. Monitor failed jobs, scheduler lag and worker leases; configure idempotent business handlers. PostgreSQL is required for distributed coordination; SQLite is insufficient.

[Full source reference](../tasks-architecture.md).
