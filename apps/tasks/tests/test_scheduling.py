"""Recurring scheduling: wall clocks, misfires, idempotency and leader races."""

from datetime import datetime, timedelta, timezone as utc
from threading import Barrier, Thread

import pytest
from django.core.management import call_command
from django.db import close_old_connections, connection, transaction
from django.test import override_settings

from apps.tasks.models import BackgroundJob, JobSchedule
from apps.tasks.schedule_domain import next_fire_after, validate_calendar
from apps.tasks.scheduler import _SCHEDULER_LOCK, fire_due, register_schedule
from apps.tasks.services import claim_next, complete, run_next

UTC = utc.utc
HANDLERS = {
    "test.ok": "apps.tasks.tests.test_jobs.job_success",
    "test.fail": "apps.tasks.tests.test_jobs.job_failure",
}


def at(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def schedule(*, name="everyday", start_at=None, **kwargs):
    return register_schedule(
        name=name,
        code=kwargs.pop("code", "test.ok"),
        payload=kwargs.pop("payload", {"item": "scheduled"}),
        hour=kwargs.pop("hour", 9),
        minute=kwargs.pop("minute", 0),
        start_at=start_at or at(2026, 10, 18),
        **kwargs,
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"timezone_name": "Not/AZone"}, "timezone"),
        ({"timezone_name": ""}, "timezone"),
        ({"hour": True}, "hour"),
        ({"hour": 24}, "hour"),
        ({"minute": -1}, "minute"),
        ({"minute": False}, "minute"),
        ({"weekdays": [0, 0]}, "unique"),
        ({"weekdays": [True]}, "weekdays"),
        ({"weekdays": [7]}, "weekdays"),
        ({"weekdays": "monday"}, "weekdays"),
    ],
)
def test_invalid_calendar(kwargs, message):
    config = {"timezone_name": "UTC", "hour": 9, "minute": 0}
    config.update(kwargs)
    with pytest.raises(ValueError, match=message):
        validate_calendar(**config)


def test_calendar_normalization_and_naive_rejected():
    assert validate_calendar(timezone_name="UTC", hour=10, minute=30, weekdays=[6, 0]) == [
        0,
        6,
    ]
    with pytest.raises(ValueError, match="timezone-aware"):
        next_fire_after(after=datetime(2026, 10, 18), timezone_name="UTC", hour=9, minute=0)


def test_daily_calendar_and_weekday_filter():
    assert next_fire_after(
        after=at(2026, 10, 18, 10), timezone_name="UTC", hour=9, minute=0
    ) == at(2026, 10, 19, 9)
    # 2026-10-18 is a Sunday: only Mondays can run.
    assert next_fire_after(
        after=at(2026, 10, 18, 10),
        timezone_name="UTC",
        hour=9,
        minute=0,
        weekdays=[0],
    ) == at(2026, 10, 19, 9)


def test_spring_dst_gap_skips_nonexistent_0230():
    # Europe/Berlin switches to summer time on 2026-03-29.
    assert next_fire_after(
        after=at(2026, 3, 28, 1, 30),
        timezone_name="Europe/Berlin",
        hour=2,
        minute=30,
    ) == at(2026, 3, 30, 0, 30)
    # A weekly Sunday 02:30 must skip the entire transition week.
    assert next_fire_after(
        after=at(2026, 3, 22, 1, 30),
        timezone_name="Europe/Berlin",
        hour=2,
        minute=30,
        weekdays=[6],
    ) == at(2026, 4, 5, 0, 30)


def test_fall_dst_fold_fires_only_first_0130():
    # America/New_York falls back on 2026-11-01.
    first = next_fire_after(
        after=at(2026, 10, 31, 12),
        timezone_name="America/New_York",
        hour=1,
        minute=30,
    )
    assert first == at(2026, 11, 1, 5, 30)
    assert next_fire_after(
        after=first, timezone_name="America/New_York", hour=1, minute=30
    ) == at(2026, 11, 2, 6, 30)
    assert next_fire_after(
        after=at(2026, 11, 1, 6), timezone_name="America/New_York", hour=1, minute=30
    ) == at(2026, 11, 2, 6, 30)


@pytest.mark.django_db
@override_settings(BACKGROUND_JOB_HANDLERS=HANDLERS)
def test_register_is_idempotent_and_namespaced_without_reset():
    first = schedule()
    assert first.next_run_at == at(2026, 10, 18, 9)
    JobSchedule.objects.filter(pk=first.pk).update(next_run_at=at(2026, 10, 20, 9))
    again = schedule(start_at=at(2026, 10, 19))
    assert again.pk == first.pk
    assert again.next_run_at == at(2026, 10, 20, 9)
    other = schedule(namespace="org:2")
    assert other.pk != first.pk
    assert JobSchedule.objects.count() == 2
    with pytest.raises(ValueError, match="Conflicting"):
        schedule(payload={"item": "changed"})
    with pytest.raises(ValueError, match="Unknown"):
        schedule(name="bad-handler", code="untrusted")
    with pytest.raises(ValueError, match="Invalid schedule name"):
        schedule(name="../../code")
    assert JobSchedule.objects.count() == 2


@pytest.mark.django_db
@override_settings(BACKGROUND_JOB_HANDLERS=HANDLERS)
def test_due_firing_into_existing_queue_and_run_worker():
    from apps.tasks.tests.test_jobs import RESULTS

    RESULTS.clear()
    definition = schedule(max_attempts=2)
    assert fire_due(now=at(2026, 10, 18, 8, 59)) == 0
    assert fire_due(now=at(2026, 10, 18, 9)) == 1
    assert fire_due(now=at(2026, 10, 18, 9)) == 0
    definition.refresh_from_db()
    assert definition.next_run_at == at(2026, 10, 19, 9)
    job = BackgroundJob.objects.get()
    assert job.available_at == at(2026, 10, 18, 9)
    assert job.max_attempts == 2
    assert job.idempotency_key.startswith(f"schedule:{definition.pk.hex}:")
    assert run_next() is True
    job.refresh_from_db()
    assert job.status == BackgroundJob.Status.SUCCEEDED
    assert RESULTS == ["scheduled"]


@pytest.mark.django_db
@override_settings(BACKGROUND_JOB_HANDLERS=HANDLERS)
def test_scheduler_coalesces_missed_runs_and_can_pause():
    definition = schedule()
    assert fire_due(now=at(2026, 11, 10, 15)) == 1
    definition.refresh_from_db()
    assert definition.next_run_at == at(2026, 11, 11, 9)
    assert fire_due(now=at(2026, 11, 10, 16)) == 0
    definition.is_enabled = False
    definition.save(update_fields=["is_enabled"])
    assert fire_due(now=at(2026, 11, 15)) == 0
    definition.is_enabled = True
    definition.save(update_fields=["is_enabled"])
    assert fire_due(now=at(2026, 11, 15)) == 1
    assert BackgroundJob.objects.count() == 2


@pytest.mark.django_db
@override_settings(BACKGROUND_JOB_HANDLERS=HANDLERS)
def test_atomic_fire_rollback_and_handler_removal():
    definition = schedule()
    with pytest.raises(RuntimeError, match="rollback"):
        with transaction.atomic():
            assert fire_due(now=at(2026, 10, 18, 9)) == 1
            raise RuntimeError("rollback")
    definition.refresh_from_db()
    assert definition.next_run_at == at(2026, 10, 18, 9)
    assert not BackgroundJob.objects.exists()
    with override_settings(BACKGROUND_JOB_HANDLERS={}):
        with pytest.raises(ValueError, match="Unknown"):
            fire_due(now=at(2026, 10, 18, 9))
    definition.refresh_from_db()
    assert definition.next_run_at == at(2026, 10, 18, 9)
    assert fire_due(now=at(2026, 10, 18, 9)) == 1
    assert BackgroundJob.objects.count() == 1


@pytest.mark.django_db
@override_settings(BACKGROUND_JOB_HANDLERS=HANDLERS)
def test_batch_limit_and_command():
    schedule(name="first")
    schedule(name="second")
    assert fire_due(now=at(2026, 10, 18, 9), limit=1) == 1
    assert BackgroundJob.objects.count() == 1
    assert fire_due(now=at(2026, 10, 18, 9), limit=1) == 1
    with pytest.raises(ValueError, match="limit"):
        fire_due(limit=0)
    with pytest.raises(ValueError, match="limit"):
        fire_due(limit=True)
    schedule(name="third", start_at=at(2020, 1, 1))
    call_command("run_schedule_dispatcher", once=True)
    assert BackgroundJob.objects.count() == 3


@pytest.mark.django_db
@override_settings(BACKGROUND_JOB_HANDLERS=HANDLERS)
def test_scheduled_failure_retries_and_stale_worker_is_fenced():
    definition = schedule(code="test.fail", max_attempts=2)
    assert fire_due(now=at(2026, 10, 18, 9)) == 1
    job = BackgroundJob.objects.get()
    first = claim_next(now=at(2026, 10, 18, 9), lease_seconds=30)
    assert first.pk == job.pk
    second = claim_next(now=at(2026, 10, 18, 9, 0) + timedelta(seconds=31), lease_seconds=30)
    assert second.pk == job.pk
    assert second.lease_token != first.lease_token
    assert not complete(job.pk, first.lease_token)
    assert complete(job.pk, second.lease_token)
    definition.refresh_from_db()
    assert definition.next_run_at == at(2026, 10, 19, 9)


@pytest.mark.django_db(transaction=True)
@override_settings(BACKGROUND_JOB_HANDLERS=HANDLERS)
def test_two_postgresql_schedulers_do_not_duplicate_firing():
    if connection.vendor != "postgresql":
        pytest.skip("Requires a real PostgreSQL transaction and advisory locks")
    definition = schedule()
    barrier = Barrier(2)
    results, errors = [], []

    def runner():
        close_old_connections()
        try:
            barrier.wait(timeout=8)
            results.append(fire_due(now=at(2026, 10, 18, 9)))
        except Exception as exc:
            errors.append(exc)
        finally:
            close_old_connections()

    workers = [Thread(target=runner) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
    assert not any(worker.is_alive() for worker in workers)
    assert errors == []
    assert sorted(results) == [0, 1]
    assert BackgroundJob.objects.count() == 1
    definition.refresh_from_db()
    assert definition.next_run_at == at(2026, 10, 19, 9)


@pytest.mark.django_db(transaction=True)
@override_settings(BACKGROUND_JOB_HANDLERS=HANDLERS)
def test_postgresql_leader_lock_is_nonblocking():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL advisory locks")
    definition = schedule()
    results, errors = [], []

    def contender():
        close_old_connections()
        try:
            results.append(fire_due(now=at(2026, 10, 18, 9)))
        except Exception as exc:
            errors.append(exc)
        finally:
            close_old_connections()

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", _SCHEDULER_LOCK)
        worker = Thread(target=contender)
        worker.start()
        worker.join(timeout=10)
        assert not worker.is_alive()
        assert errors == []
        assert results == [0]
    assert fire_due(now=at(2026, 10, 18, 9)) == 1
    assert BackgroundJob.objects.count() == 1
    definition.refresh_from_db()
    assert definition.next_run_at == at(2026, 10, 19, 9)
