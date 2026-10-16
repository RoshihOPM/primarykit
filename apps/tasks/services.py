"""Transactional, internal-only task application service.

Execution is at-least-once. Only code registered in BACKGROUND_JOB_HANDLERS can run.
"""

import uuid
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.module_loading import import_string

from apps.tasks.domain import require_aware_datetime, retry_seconds, validate_job
from apps.tasks.models import BackgroundJob


def _handlers() -> dict[str, str]:
    handlers = getattr(settings, "BACKGROUND_JOB_HANDLERS", {})
    if not isinstance(handlers, dict):
        raise ValueError("BACKGROUND_JOB_HANDLERS must be a dict")
    return handlers


def enqueue(
    *,
    code: str,
    payload: dict,
    namespace: str = "default",
    idempotency_key: str | None = None,
    run_after=None,
    max_attempts: int = 5,
) -> BackgroundJob:
    """Insert into the caller's transaction; never publish a job before commit."""
    data = validate_job(
        namespace=namespace,
        code=code,
        payload=payload,
        key=idempotency_key,
        attempts=max_attempts,
    )
    if code not in _handlers():
        raise ValueError(f"Unknown internal job code: {code}")
    if run_after is not None:
        require_aware_datetime(run_after)
    schedule = run_after or timezone.now()
    kwargs = {
        "code": code,
        "payload": data,
        "namespace": namespace,
        "idempotency_key": idempotency_key,
        "available_at": schedule,
        "max_attempts": max_attempts,
    }

    with transaction.atomic():
        if idempotency_key is None:
            return BackgroundJob.objects.create(**kwargs)
        try:
            # The nested savepoint allows a safe read after a unique-key race.
            with transaction.atomic():
                return BackgroundJob.objects.create(**kwargs)
        except IntegrityError:
            existing = BackgroundJob.objects.get(
                namespace=namespace, idempotency_key=idempotency_key
            )
            if (
                existing.code != code
                or existing.payload != data
                or existing.max_attempts != max_attempts
                or (run_after is not None and existing.available_at != schedule)
            ):
                raise ValueError("Conflicting idempotency key") from None
            return existing


def claim_next(*, lease_seconds: int = 900, now=None) -> BackgroundJob | None:
    """Claim once using a PostgreSQL SKIP LOCKED row lease."""
    if type(lease_seconds) is not int or lease_seconds < 30:
        raise ValueError("lease_seconds must be at least 30")
    now = now or timezone.now()
    expiry = now - timedelta(seconds=lease_seconds)
    with transaction.atomic():
        BackgroundJob.objects.filter(
            status=BackgroundJob.Status.RUNNING,
            locked_at__lte=expiry,
            attempts__gte=F("max_attempts"),
        ).update(
            status=BackgroundJob.Status.FAILED,
            lease_token=None,
            locked_at=None,
            last_error="LeaseExpired",
            updated_at=now,
        )
        waiting = BackgroundJob.objects.filter(
            Q(status=BackgroundJob.Status.PENDING, available_at__lte=now)
            | Q(
                status=BackgroundJob.Status.RUNNING,
                locked_at__lte=expiry,
                attempts__lt=F("max_attempts"),
            )
        ).order_by("available_at", "created_at")
        if connection.features.has_select_for_update_skip_locked:
            waiting = waiting.select_for_update(skip_locked=True)
        else:
            waiting = waiting.select_for_update()
        job = waiting.first()
        if job is None:
            return None
        job.status = BackgroundJob.Status.RUNNING
        job.attempts += 1
        job.lease_token = uuid.uuid4()
        job.locked_at = now
        job.save(update_fields=("status", "attempts", "lease_token", "locked_at", "updated_at"))
        return job


def complete(job_id, token) -> bool:
    """Lease token prevents stale workers from acknowledging newer attempts."""
    with transaction.atomic():
        job = BackgroundJob.objects.select_for_update().get(pk=job_id)
        if job.status != BackgroundJob.Status.RUNNING or job.lease_token != token:
            return False
        job.status = BackgroundJob.Status.SUCCEEDED
        job.lease_token = None
        job.locked_at = None
        job.last_error = ""
        job.save(update_fields=("status", "lease_token", "locked_at", "last_error", "updated_at"))
        return True


def fail(job_id, token, error: Exception, *, now=None) -> bool:
    now = now or timezone.now()
    with transaction.atomic():
        job = BackgroundJob.objects.select_for_update().get(pk=job_id)
        if job.status != BackgroundJob.Status.RUNNING or job.lease_token != token:
            return False
        job.status = (
            BackgroundJob.Status.FAILED
            if job.attempts >= job.max_attempts
            else BackgroundJob.Status.PENDING
        )
        if job.status == BackgroundJob.Status.PENDING:
            job.available_at = now + timedelta(seconds=retry_seconds(job.attempts))
        job.lease_token = None
        job.locked_at = None
        # Never persist exception text: it may contain secrets or personal data.
        job.last_error = type(error).__name__[:160]
        job.save(
            update_fields=(
                "status",
                "available_at",
                "lease_token",
                "locked_at",
                "last_error",
                "updated_at",
            )
        )
        return True


def run_next(*, lease_seconds: int = 900) -> bool:
    """Run one trusted synchronous handler(payload); false means nothing available."""
    job = claim_next(lease_seconds=lease_seconds)
    if job is None:
        return False
    try:
        handler_path = _handlers().get(job.code)
        if not isinstance(handler_path, str) or not handler_path:
            raise ValueError("No registered handler for job")
        handler = import_string(handler_path)
        handler(job.payload)
    except Exception as exc:
        fail(job.id, job.lease_token, exc)
    else:
        complete(job.id, job.lease_token)
    return True
