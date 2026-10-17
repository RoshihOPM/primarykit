"""Admin-approved retention state transitions and atomic, retry-safe execution."""

import uuid

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from apps.audit.services import record_event
from apps.privacy.domain import (
    HOLD_REASONS,
    load_policy,
    planned_execution,
    validate_reference,
)
from apps.privacy.models import PrivacyRequest, PrivacySubject
from apps.tasks.services import enqueue

JOB_CODE = "privacy.execute"


def _admin(actor):
    if not (
        actor is not None
        and getattr(actor, "is_authenticated", False)
        and actor.pk is not None
        and actor.is_active
        and actor.is_superuser
    ):
        raise PermissionDenied("A verified active superuser is required")


def _policy(code, kind, action):
    config = getattr(settings, "PRIVACY_RETENTION_POLICIES", {})
    if not isinstance(config, dict) or code not in config:
        raise ValueError("Unknown client retention policy")
    policy = load_policy(code, config[code])
    if policy.kind != kind or action not in policy.actions:
        raise ValueError("Action or subject kind denied by policy")
    return policy


def _event(request, old_status, *, actor=None, action="status"):
    record_event(
        action=f"privacy.{action}",
        target_type="privacy.PrivacyRequest",
        target_id=request.pk,
        actor=actor,
        changes={
            "state": {"before": old_status, "after": request.status},
            "policy": request.policy_code,
            "operation": request.action,
        },
    )


def _hold_event(subject, *, actor, action):
    record_event(
        action=f"privacy.hold.{action}",
        target_type="privacy.PrivacySubject",
        target_id=subject.pk,
        actor=actor,
        changes={"reason": subject.hold_reason},
    )


def _queue(request):
    """Requires an explicit setting AND registered trusted Tasks handler."""
    enqueue(
        code=JOB_CODE,
        namespace="privacy",
        payload={"request_id": str(request.pk), "revision": request.revision},
        idempotency_key=f"{request.pk}:{request.revision}",
        run_after=request.execute_after,
    )


def preview(*, scope, kind, subject_id, policy_code, action, actor, now=None):
    """A dry-run calculates eligibility without invoking handlers or writing rows."""
    _admin(actor)
    subject_id, _ = validate_reference(scope, kind, subject_id)
    policy = _policy(policy_code, kind, action)
    now = now or timezone.now()
    planned = planned_execution(now, policy)
    held = PrivacySubject.objects.filter(
        scope=scope, kind=kind, reference=subject_id, legal_hold=True
    ).exists()
    return {
        "scope": scope,
        "kind": kind,
        "subject_id": str(subject_id),
        "policy": policy_code,
        "action": action,
        "execute_after": planned,
        "legal_hold": held,
        "automatic": bool(getattr(settings, "PRIVACY_AUTO_EXECUTION_ENABLED", False)),
        "dry_run": True,
    }


def request_retention(
    *, scope, kind, subject_id, policy_code, action, idempotency_key, actor, dry_run=False, now=None
):
    _admin(actor)
    subject_id, key = validate_reference(scope, kind, subject_id, idempotency_key)
    if key is None:
        raise ValueError("A UUID idempotency key is required")
    policy = _policy(policy_code, kind, action)
    now = now or timezone.now()
    after = planned_execution(now, policy)
    if dry_run:
        return preview(
            scope=scope,
            kind=kind,
            subject_id=subject_id,
            policy_code=policy_code,
            action=action,
            actor=actor,
            now=now,
        )
    with transaction.atomic():
        subject, _ = PrivacySubject.objects.get_or_create(
            scope=scope, kind=kind, reference=subject_id
        )
        subject = PrivacySubject.objects.select_for_update().get(pk=subject.pk)
        prior = PrivacyRequest.objects.filter(idempotency_key=key).first()
        if prior is not None:
            if (
                prior.subject_id != subject.pk
                or prior.policy_code != policy_code
                or prior.action != action
                or prior.policy_fingerprint != policy.fingerprint
            ):
                raise ValueError("Conflicting idempotency key")
            return prior
        if PrivacyRequest.objects.filter(
            subject=subject, status__in=(PrivacyRequest.Status.PENDING, PrivacyRequest.Status.HELD)
        ).exists():
            raise ValueError("Subject already has an active privacy request")
        status = PrivacyRequest.Status.HELD if subject.legal_hold else PrivacyRequest.Status.PENDING
        try:
            with transaction.atomic():
                request = PrivacyRequest.objects.create(
                    subject=subject,
                    idempotency_key=key,
                    policy_code=policy_code,
                    policy_fingerprint=policy.fingerprint,
                    action=action,
                    status=status,
                    execute_after=after,
                )
        except IntegrityError:
            # Concurrent replay may have been inserted under a different subject lock.
            prior = PrivacyRequest.objects.get(idempotency_key=key)
            if (
                prior.subject_id != subject.pk
                or prior.policy_code != policy_code
                or prior.action != action
                or prior.policy_fingerprint != policy.fingerprint
            ):
                raise ValueError("Conflicting idempotency key") from None
            return prior
        _event(request, None, actor=actor, action="requested")
        if status == PrivacyRequest.Status.PENDING and getattr(
            settings, "PRIVACY_AUTO_EXECUTION_ENABLED", False
        ):
            _queue(request)
        return request


def set_legal_hold(*, scope, kind, subject_id, reason, actor):
    _admin(actor)
    subject_id, _ = validate_reference(scope, kind, subject_id)
    if not isinstance(reason, str) or reason not in HOLD_REASONS:
        raise ValueError("Use an approved, non-PII legal hold reason code")
    with transaction.atomic():
        subject, _ = PrivacySubject.objects.get_or_create(
            scope=scope, kind=kind, reference=subject_id
        )
        subject = PrivacySubject.objects.select_for_update().get(pk=subject.pk)
        if subject.legal_hold and subject.hold_reason == reason:
            return subject
        subject.legal_hold, subject.hold_reason = True, reason
        subject.save(update_fields=("legal_hold", "hold_reason"))
        _hold_event(subject, actor=actor, action="placed")
        for request in PrivacyRequest.objects.select_for_update().filter(
            subject=subject, status=PrivacyRequest.Status.PENDING
        ):
            old = request.status
            request.status = PrivacyRequest.Status.HELD
            request.revision += 1
            request.save(update_fields=("status", "revision", "updated_at"))
            _event(request, old, actor=actor, action="held")
        return subject


def release_legal_hold(*, scope, kind, subject_id, actor):
    _admin(actor)
    subject_id, _ = validate_reference(scope, kind, subject_id)
    with transaction.atomic():
        subject = PrivacySubject.objects.select_for_update().get(
            scope=scope, kind=kind, reference=subject_id
        )
        if not subject.legal_hold:
            return subject
        subject.legal_hold, subject.hold_reason = False, ""
        subject.save(update_fields=("legal_hold", "hold_reason"))
        _hold_event(subject, actor=actor, action="released")
        for request in PrivacyRequest.objects.select_for_update().filter(
            subject=subject, status=PrivacyRequest.Status.HELD
        ):
            old = request.status
            request.status = PrivacyRequest.Status.PENDING
            request.revision += 1
            request.save(update_fields=("status", "revision", "updated_at"))
            _event(request, old, actor=actor, action="released")
            if getattr(settings, "PRIVACY_AUTO_EXECUTION_ENABLED", False):
                _queue(request)
        return subject


def _lock_request(request_id):
    # Lock ordering is always subject -> request across all transitions.
    subject_id = PrivacyRequest.objects.values_list("subject_id", flat=True).get(pk=request_id)
    subject = PrivacySubject.objects.select_for_update().get(pk=subject_id)
    request = PrivacyRequest.objects.select_for_update().get(pk=request_id)
    return subject, request


def cancel_request(*, request_id, actor):
    _admin(actor)
    with transaction.atomic():
        _, request = _lock_request(request_id)
        if request.status == PrivacyRequest.Status.CANCELLED:
            return request
        if request.status == PrivacyRequest.Status.COMPLETED:
            raise ValueError("Completed privacy action cannot be undone")
        old = request.status
        request.status = PrivacyRequest.Status.CANCELLED
        request.revision += 1
        request.save(update_fields=("status", "revision", "updated_at"))
        _event(request, old, actor=actor, action="cancelled")
        return request


def _execute(request_id, *, now=None, revision=None, automatic=False):
    now = now or timezone.now()
    with transaction.atomic():
        subject, request = _lock_request(request_id)
        if revision is not None and request.revision != revision:
            return False  # Stale Tasks delivery after hold/release/cancellation.
        if request.status != PrivacyRequest.Status.PENDING or subject.legal_hold:
            return False
        if automatic and not getattr(settings, "PRIVACY_AUTO_EXECUTION_ENABLED", False):
            raise PermissionDenied("Automatic privacy processing is disabled")
        if now < request.execute_after:
            raise ValueError("Retention grace window has not expired")
        policy = _policy(request.policy_code, subject.kind, request.action)
        if policy.fingerprint != request.policy_fingerprint:
            raise ValueError("Retention policy changed; request needs manual review")
        # Client handler must mutate its own DB rows idempotently, in this transaction.
        # No HTTP, broker or irreversible external side effects in the handler.
        handler = import_string(policy.handler)
        handler(
            scope=subject.scope,
            kind=subject.kind,
            subject_id=subject.reference,
            action=request.action,
        )
        old = request.status
        request.status = PrivacyRequest.Status.COMPLETED
        request.completed_at = now
        request.save(update_fields=("status", "completed_at", "updated_at"))
        _event(request, old, action="completed")
        return True


def execute_manually(*, request_id, actor, now=None):
    _admin(actor)
    return _execute(request_id, now=now)


def process_retention_job(payload):
    """Trusted Tasks handler. It is safe to receive a stale or repeated delivery."""
    if not isinstance(payload, dict) or set(payload) != {"request_id", "revision"}:
        raise ValueError("Invalid privacy job payload")
    try:
        request_id = uuid.UUID(payload["request_id"])
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Invalid privacy request identifier") from exc
    revision = payload["revision"]
    if type(revision) is not int or revision < 0:
        raise ValueError("Invalid privacy job revision")
    return _execute(request_id, revision=revision, automatic=True)
