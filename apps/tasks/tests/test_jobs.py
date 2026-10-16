"""Portable tasks: database state, idempotency, leases, and trusted worker."""

from datetime import timedelta
from threading import Barrier, Thread

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction
from django.test import override_settings
from django.utils import timezone

from apps.tasks.domain import retry_seconds, validate_job
from apps.tasks.models import BackgroundJob
from apps.tasks.services import claim_next, complete, enqueue, run_next

RESULTS = []
HANDLERS = {
    "test.ok": "apps.tasks.tests.test_jobs.job_success",
    "test.fail": "apps.tasks.tests.test_jobs.job_failure",
}


def job_success(payload):
    RESULTS.append(payload["item"])


def job_failure(payload):
    raise RuntimeError("Never store credentials from exceptions")


def test_pure_domain_validations():
    assert retry_seconds(1) == 2
    assert retry_seconds(20) == 3600
    assert validate_job(
        code="test.ok", namespace="org:123", payload={"id": "a"}, key="key-1", attempts=2
    ) == {"id": "a"}
    for payload in (["not a dict"], {"bad": object()}, {"x": float("nan")}):
        with pytest.raises(ValueError):
            validate_job(code="test.ok", namespace="default", payload=payload, key=None, attempts=2)
    with pytest.raises(ValueError):
        validate_job(code="test.ok", namespace="default", payload={}, key="x", attempts=True)


@pytest.mark.django_db
@override_settings(BACKGROUND_JOB_HANDLERS=HANDLERS)
def test_durable_queue_idempotency_and_namespace_isolation():
    first = enqueue(code="test.ok", payload={"item": 1}, idempotency_key="req-1")
    assert enqueue(code="test.ok", payload={"item": 1}, idempotency_key="req-1").pk == first.pk
    assert (
        enqueue(code="test.ok", payload={"item": 1}, idempotency_key="req-1", namespace="org:2").pk
        != first.pk
    )
    assert BackgroundJob.objects.count() == 2
    with pytest.raises(ValueError, match="Conflicting"):
        enqueue(code="test.ok", payload={"item": 2}, idempotency_key="req-1")
    with pytest.raises(ValueError, match="Unknown"):
        enqueue(code="untrusted", payload={})
    assert BackgroundJob.objects.count() == 2


@pytest.mark.django_db
@override_settings(BACKGROUND_JOB_HANDLERS=HANDLERS)
def test_worker_success_and_replay_protection():
    RESULTS.clear()
    job = enqueue(code="test.ok", payload={"item": "demo"})
    assert run_next() is True
    assert run_next() is False
    job.refresh_from_db()
    assert job.status == BackgroundJob.Status.SUCCEEDED
    assert job.attempts == 1
    assert RESULTS == ["demo"]


@pytest.mark.django_db
@override_settings(BACKGROUND_JOB_HANDLERS=HANDLERS)
def test_worker_failure_retry_and_dead_letter_state():
    job = enqueue(code="test.fail", payload={"secret": "never-log"}, max_attempts=2)
    assert run_next()
    job.refresh_from_db()
    assert job.status == BackgroundJob.Status.PENDING
    assert job.last_error == "RuntimeError"
    assert "never-log" not in job.last_error
    BackgroundJob.objects.filter(pk=job.pk).update(
        available_at=timezone.now() - timedelta(seconds=1)
    )
    assert run_next()
    job.refresh_from_db()
    assert job.status == BackgroundJob.Status.FAILED
    assert job.attempts == 2
    assert run_next() is False


@pytest.mark.django_db
@override_settings(BACKGROUND_JOB_HANDLERS=HANDLERS)
def test_stale_worker_token_cannot_complete_reclaimed_job():
    moment = timezone.now()
    job = enqueue(code="test.ok", payload={"item": "lease"}, run_after=moment)
    first = claim_next(now=moment, lease_seconds=30)
    assert first.pk == job.pk
    token = first.lease_token
    assert claim_next(now=moment + timedelta(seconds=5), lease_seconds=30) is None
    second = claim_next(now=moment + timedelta(seconds=31), lease_seconds=30)
    assert second.pk == job.pk
    assert second.lease_token != token
    assert not complete(job.pk, token)
    assert complete(job.pk, second.lease_token)


@pytest.mark.django_db
@override_settings(BACKGROUND_JOB_HANDLERS=HANDLERS)
def test_jobs_rollback_with_parent_transaction():
    with pytest.raises(RuntimeError, match="rollback"):
        with transaction.atomic():
            enqueue(code="test.ok", payload={}, idempotency_key="rolled-back")
            raise RuntimeError("rollback")
    assert not BackgroundJob.objects.filter(idempotency_key="rolled-back").exists()


@pytest.mark.django_db
@override_settings(BACKGROUND_JOB_HANDLERS=HANDLERS)
def test_management_worker_runs_only_when_invoked():
    RESULTS.clear()
    enqueue(code="test.ok", payload={"item": "cmd"})
    call_command("run_background_jobs", once=True)
    assert RESULTS == ["cmd"]


@pytest.mark.django_db(transaction=True)
@override_settings(BACKGROUND_JOB_HANDLERS=HANDLERS)
def test_postgresql_two_workers_claim_a_single_job():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row-lock integration")
    job = enqueue(code="test.ok", payload={"item": "race"})
    barrier = Barrier(2)
    claimed, errors = [], []

    def runner():
        from django.db import close_old_connections

        close_old_connections()
        try:
            barrier.wait(timeout=8)
            result = claim_next()
            if result:
                claimed.append(result.pk)
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
    assert not errors
    assert claimed == [job.pk]


@pytest.mark.django_db
@override_settings(BACKGROUND_JOB_HANDLERS={})
def test_no_worker_handler_by_default():
    assert settings.BACKGROUND_JOB_HANDLERS == {}
    with pytest.raises(ValueError, match="Unknown"):
        enqueue(code="test.ok", payload={})
