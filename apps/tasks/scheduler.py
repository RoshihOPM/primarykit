"""PostgreSQL-coordinated recurring scheduler using the existing Tasks queue.

No second delivery table or broker. The advisory lock is transaction-scoped:
a crash rolls back both the BackgroundJob inserts and cursor advancement.
"""

from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.tasks.domain import JOB_CODE, require_aware_datetime, validate_job
from apps.tasks.models import JobSchedule
from apps.tasks.schedule_domain import next_fire_after, validate_calendar
from apps.tasks.services import _handlers, enqueue

# Application-wide lock scoped by the PostgreSQL database (two signed int32s).
_SCHEDULER_LOCK = (0x5052494D, 47)


def register_schedule(
    *,
    name: str,
    code: str,
    payload: dict,
    hour: int,
    minute: int,
    timezone_name: str = "UTC",
    weekdays=None,
    namespace: str = "default",
    max_attempts: int = 5,
    start_at=None,
) -> JobSchedule:
    """Register immutable schedule configuration; repeats are idempotent.

    `start_at` is the earliest eligible instant (inclusive) for a new schedule.
    Disabling, enabling or editing an existing schedule is an explicit ORM
    operation in the copied client, not an implicit register side effect.
    """
    if not isinstance(name, str) or not JOB_CODE.fullmatch(name):
        raise ValueError("Invalid schedule name")
    data = validate_job(
        namespace=namespace, code=code, payload=payload, key=None, attempts=max_attempts
    )
    if code not in _handlers():
        raise ValueError(f"Unknown internal job code: {code}")
    days = validate_calendar(
        timezone_name=timezone_name, hour=hour, minute=minute, weekdays=weekdays
    )
    if start_at is None:
        start_at = timezone.now()
    require_aware_datetime(start_at)
    first = next_fire_after(
        after=start_at - timedelta(microseconds=1),
        timezone_name=timezone_name,
        hour=hour,
        minute=minute,
        weekdays=days,
    )
    configuration = {
        "code": code,
        "payload": data,
        "timezone_name": timezone_name,
        "hour": hour,
        "minute": minute,
        "weekdays": days,
        "max_attempts": max_attempts,
    }
    with transaction.atomic():
        try:
            with transaction.atomic():
                return JobSchedule.objects.create(
                    namespace=namespace, name=name, next_run_at=first, **configuration
                )
        except IntegrityError:
            existing = JobSchedule.objects.select_for_update().get(
                namespace=namespace, name=name
            )
            if any(getattr(existing, field) != value for field, value in configuration.items()):
                raise ValueError("Conflicting schedule configuration") from None
            return existing


def _leader_acquired() -> bool:
    """Non-blocking transaction-level election; SQLite is only a test fallback."""
    if connection.vendor == "sqlite":
        return True
    if connection.vendor != "postgresql":
        raise RuntimeError("Scheduled jobs require PostgreSQL")
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_xact_lock(%s, %s)", _SCHEDULER_LOCK)
        return bool(cursor.fetchone()[0])


def fire_due(*, now=None, limit: int = 100) -> int:
    """Atomically enqueue at most `limit` due occurrences as a scheduler leader.

    Misfire policy: coalesce an outage to one job for the oldest due instant
    per schedule and skip additional missed occurrences. A schedule's next
    local wall-clock occurrence is computed strictly after `now`.
    """
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be an integer between 1 and 1000")
    if now is None:
        now = timezone.now()
    require_aware_datetime(now)

    with transaction.atomic():
        if not _leader_acquired():
            return 0
        due = JobSchedule.objects.filter(
            is_enabled=True, next_run_at__lte=now
        ).order_by("next_run_at", "pk")
        if connection.features.has_select_for_update_skip_locked:
            due = due.select_for_update(skip_locked=True)
        else:
            due = due.select_for_update()

        count = 0
        for schedule in due[:limit]:
            fire_at = schedule.next_run_at
            # The schedule UUID and planned UTC second identify this firing.
            # Concurrent or retried scheduler transactions cannot duplicate it.
            key = f"schedule:{schedule.pk.hex}:{int(fire_at.timestamp())}"
            enqueue(
                namespace=schedule.namespace,
                code=schedule.code,
                payload=schedule.payload,
                idempotency_key=key,
                run_after=fire_at,
                max_attempts=schedule.max_attempts,
            )
            schedule.next_run_at = next_fire_after(
                after=max(now, fire_at),
                timezone_name=schedule.timezone_name,
                hour=schedule.hour,
                minute=schedule.minute,
                weekdays=schedule.weekdays,
            )
            schedule.save(update_fields=("next_run_at", "updated_at"))
            count += 1
        return count
