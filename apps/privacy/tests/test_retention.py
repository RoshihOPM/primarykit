"""Privacy retention contracts, negative paths, retries and PostgreSQL races."""

import uuid
from datetime import timedelta
from threading import Barrier, Thread

import pytest
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection, connections
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.privacy.domain import load_policy, planned_execution, validate_reference
from apps.privacy.models import PrivacyRequest, PrivacySubject
from apps.privacy.services import (
    cancel_request,
    execute_manually,
    preview,
    process_retention_job,
    release_legal_hold,
    request_retention,
    set_legal_hold,
)
from apps.tasks.models import BackgroundJob
from apps.tasks.services import run_next
from apps.users.models import User

POLICIES = {
    "person": {
        "kind": "person",
        "actions": ("redact", "anonymize", "delete"),
        "grace_days": 0,
        "handler": "apps.privacy.tests.test_retention.redact_person",
    },
    "slow": {
        "kind": "person",
        "actions": ("redact",),
        "grace_days": 3,
        "handler": "apps.privacy.tests.test_retention.redact_person",
    },
    "broken": {
        "kind": "person",
        "actions": ("redact",),
        "grace_days": 0,
        "handler": "apps.privacy.tests.test_retention.fail_transactionally",
    },
}


def redact_person(*, scope, kind, subject_id, action):
    assert kind == "person"
    assert scope.startswith("client:")
    assert action in {"redact", "anonymize", "delete"}
    # Client owns this explicit field-level rule; no generic or cascaded delete.
    User.objects.filter(pk=subject_id).update(first_name="")


def fail_transactionally(*, scope, kind, subject_id, action):
    User.objects.filter(pk=subject_id).update(first_name="")
    raise RuntimeError("test PII should not be captured by Tasks")


@pytest.fixture(autouse=True)
def client_policies(settings):
    settings.PRIVACY_RETENTION_POLICIES = POLICIES
    settings.PRIVACY_AUTO_EXECUTION_ENABLED = False


@pytest.fixture
def administrator(db):
    return User.objects.create_user(
        email="privacy-admin@example.com",
        password="strong-pass-123",
        is_superuser=True,
        is_staff=True,
        email_verified=True,
    )


@pytest.fixture
def subject(db):
    return User.objects.create_user(
        email="privacy-target@example.com",
        password="strong-pass-123",
        first_name="Confidential",
        email_verified=True,
    )


def make_request(administrator, subject, **kwargs):
    return request_retention(
        scope="client:one",
        kind="person",
        subject_id=subject.pk,
        policy_code="person",
        action="redact",
        idempotency_key=uuid.uuid4(),
        actor=administrator,
        **kwargs,
    )


def test_domain_policy_validation_and_grace():
    policy = load_policy("person", POLICIES["person"])
    assert policy.actions == {"redact", "delete", "anonymize"}
    assert planned_execution(timezone.now(), policy) <= timezone.now()
    assert validate_reference("client:one", "person", uuid.uuid4())[1] is None
    with pytest.raises(ValueError):
        validate_reference("client:alice@example.test", "person", uuid.uuid4())
    with pytest.raises(ValueError):
        validate_reference("client:one", "person", "email@example.test")
    with pytest.raises(ValueError):
        load_policy("person", {**POLICIES["person"], "grace_days": True})
    with pytest.raises(ValueError):
        load_policy("person", {**POLICIES["person"], "actions": ("erase_everything",)})
    with pytest.raises(ValueError):
        load_policy("person", {**POLICIES["person"], "handler": "invalid path"})
    with pytest.raises(ValueError):
        planned_execution(timezone.now().replace(tzinfo=None), policy)


@pytest.mark.django_db
def test_dry_run_never_writes_or_calls_handler(administrator, subject):
    plan = make_request(administrator, subject, dry_run=True)
    assert plan["dry_run"] and not plan["automatic"]
    assert plan["action"] == "redact"
    assert not PrivacySubject.objects.exists()
    assert not PrivacyRequest.objects.exists()
    assert not AuditEvent.objects.filter(action__startswith="privacy.").exists()
    assert not BackgroundJob.objects.exists()
    subject.refresh_from_db()
    assert subject.first_name == "Confidential"
    assert preview(
        scope="client:one",
        kind="person",
        subject_id=subject.pk,
        policy_code="person",
        action="redact",
        actor=administrator,
    )["dry_run"]


@pytest.mark.django_db
def test_admin_only_and_deny_unknown_policy(administrator, subject):
    regular = subject
    with pytest.raises(PermissionDenied):
        make_request(regular, subject)
    regular.is_superuser = True
    regular.is_active = False
    with pytest.raises(PermissionDenied):
        make_request(regular, subject)
    with pytest.raises(ValueError, match="Unknown"):
        request_retention(
            scope="client:one",
            kind="person",
            subject_id=subject.pk,
            policy_code="unknown",
            action="delete",
            idempotency_key=uuid.uuid4(),
            actor=administrator,
        )
    with pytest.raises(ValueError, match="denied"):
        request_retention(
            scope="client:one",
            kind="organization",
            subject_id=subject.pk,
            policy_code="person",
            action="delete",
            idempotency_key=uuid.uuid4(),
            actor=administrator,
        )
    assert not PrivacyRequest.objects.exists()


@pytest.mark.django_db
def test_no_automatic_deletion_and_manual_completion(administrator, subject):
    request = make_request(administrator, subject)
    assert request.status == PrivacyRequest.Status.PENDING
    assert BackgroundJob.objects.count() == 0
    assert execute_manually(request_id=request.pk, actor=administrator)
    assert not execute_manually(request_id=request.pk, actor=administrator)
    subject.refresh_from_db()
    request.refresh_from_db()
    assert subject.first_name == ""
    assert User.objects.filter(pk=subject.pk).exists()  # no unconditional cascade
    assert request.status == PrivacyRequest.Status.COMPLETED
    with pytest.raises(ValueError, match="cannot be undone"):
        cancel_request(request_id=request.pk, actor=administrator)
    assert AuditEvent.objects.filter(action="privacy.requested").count() == 1
    assert AuditEvent.objects.filter(action="privacy.completed").count() == 1
    assert not AuditEvent.objects.filter(changes__icontains="Confidential").exists()


@pytest.mark.django_db
def test_idempotency_conflict_scope_and_only_one_active(administrator, subject):
    key = uuid.uuid4()
    arguments = dict(
        scope="client:one",
        kind="person",
        subject_id=subject.pk,
        policy_code="person",
        action="redact",
        idempotency_key=key,
        actor=administrator,
    )
    first = request_retention(**arguments)
    assert request_retention(**arguments).pk == first.pk
    with pytest.raises(ValueError, match="Conflicting"):
        request_retention(**{**arguments, "scope": "client:two"})
    with pytest.raises(ValueError, match="active"):
        make_request(administrator, subject)
    assert PrivacyRequest.objects.count() == 1


@pytest.mark.django_db
def test_grace_prevents_early_execution_and_policy_drift(administrator, subject, settings):
    request = request_retention(
        scope="client:one",
        kind="person",
        subject_id=subject.pk,
        policy_code="slow",
        action="redact",
        idempotency_key=uuid.uuid4(),
        actor=administrator,
    )
    with pytest.raises(ValueError, match="grace"):
        execute_manually(request_id=request.pk, actor=administrator)
    settings.PRIVACY_RETENTION_POLICIES = {
        **POLICIES,
        "slow": {**POLICIES["slow"], "grace_days": 5},
    }
    with pytest.raises(ValueError, match="changed"):
        execute_manually(
            request_id=request.pk,
            actor=administrator,
            now=request.execute_after + timedelta(seconds=1),
        )
    request.refresh_from_db()
    assert request.status == PrivacyRequest.Status.PENDING
    subject.refresh_from_db()
    assert subject.first_name == "Confidential"


@pytest.mark.django_db
def test_legal_hold_before_and_during_request(administrator, subject):
    set_legal_hold(
        scope="client:one",
        kind="person",
        subject_id=subject.pk,
        reason="legal",
        actor=administrator,
    )
    request = make_request(administrator, subject)
    assert request.status == PrivacyRequest.Status.HELD
    assert not execute_manually(request_id=request.pk, actor=administrator)
    assert preview(
        scope="client:one",
        kind="person",
        subject_id=subject.pk,
        policy_code="person",
        action="redact",
        actor=administrator,
    )["legal_hold"]
    release_legal_hold(
        scope="client:one", kind="person", subject_id=subject.pk, actor=administrator
    )
    request.refresh_from_db()
    assert request.status == PrivacyRequest.Status.PENDING
    assert execute_manually(request_id=request.pk, actor=administrator)
    assert AuditEvent.objects.filter(action="privacy.hold.placed").exists()
    assert AuditEvent.objects.filter(action="privacy.hold.released").exists()


@pytest.mark.django_db
def test_cancelled_request_is_immutable_to_stale_jobs(administrator, subject, settings):
    settings.PRIVACY_AUTO_EXECUTION_ENABLED = True
    request = make_request(administrator, subject)
    assert BackgroundJob.objects.count() == 1
    cancel_request(request_id=request.pk, actor=administrator)
    assert process_retention_job({"request_id": str(request.pk), "revision": 0}) is False
    assert run_next()
    request.refresh_from_db()
    assert request.status == PrivacyRequest.Status.CANCELLED
    subject.refresh_from_db()
    assert subject.first_name == "Confidential"
    assert cancel_request(request_id=request.pk, actor=administrator).status == (
        PrivacyRequest.Status.CANCELLED
    )


@pytest.mark.django_db
def test_hold_invalidates_enqueued_generation(administrator, subject, settings):
    settings.PRIVACY_AUTO_EXECUTION_ENABLED = True
    request = make_request(administrator, subject)
    set_legal_hold(
        scope="client:one",
        kind="person",
        subject_id=subject.pk,
        reason="dispute",
        actor=administrator,
    )
    assert process_retention_job({"request_id": str(request.pk), "revision": 0}) is False
    assert run_next()
    subject.refresh_from_db()
    assert subject.first_name == "Confidential"
    release_legal_hold(
        scope="client:one", kind="person", subject_id=subject.pk, actor=administrator
    )
    assert BackgroundJob.objects.count() == 2
    assert run_next()
    request.refresh_from_db()
    assert request.status == PrivacyRequest.Status.COMPLETED
    assert not run_next()


@pytest.mark.django_db
def test_automatic_flag_is_checked_at_execution(administrator, subject, settings):
    settings.PRIVACY_AUTO_EXECUTION_ENABLED = True
    request = make_request(administrator, subject)
    settings.PRIVACY_AUTO_EXECUTION_ENABLED = False
    with pytest.raises(PermissionDenied):
        process_retention_job({"request_id": str(request.pk), "revision": 0})
    assert execute_manually(request_id=request.pk, actor=administrator)


@pytest.mark.django_db
def test_failed_handler_rolls_back_and_jobs_can_retry(administrator, subject, settings):
    settings.PRIVACY_AUTO_EXECUTION_ENABLED = True
    request = request_retention(
        scope="client:one",
        kind="person",
        subject_id=subject.pk,
        policy_code="broken",
        action="redact",
        idempotency_key=uuid.uuid4(),
        actor=administrator,
    )
    assert run_next()
    request.refresh_from_db()
    subject.refresh_from_db()
    assert request.status == PrivacyRequest.Status.PENDING
    assert subject.first_name == "Confidential"
    job = BackgroundJob.objects.get(code="privacy.execute")
    assert job.last_error == "RuntimeError"
    assert "Confidential" not in job.last_error
    assert not AuditEvent.objects.filter(action="privacy.completed").exists()


@pytest.mark.django_db
def test_rejects_untrusted_job_payload_and_hold_reasons(administrator, subject):
    for payload in (
        {},
        {"request_id": "fake", "revision": 0},
        {"request_id": str(uuid.uuid4()), "revision": True},
    ):
        with pytest.raises(ValueError):
            process_retention_job(payload)
    with pytest.raises(ValueError):
        set_legal_hold(
            scope="client:one",
            kind="person",
            subject_id=subject.pk,
            reason="customer email address",
            actor=administrator,
        )


@pytest.mark.django_db(transaction=True)
def test_postgresql_simultaneous_replay_yields_one_request(administrator, subject):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL select_for_update race test")
    key = uuid.uuid4()
    barrier = Barrier(2)
    ids, errors = [], []

    def runner():
        close_old_connections()
        try:
            barrier.wait(timeout=8)
            op = request_retention(
                scope="client:one",
                kind="person",
                subject_id=subject.pk,
                policy_code="person",
                action="redact",
                idempotency_key=key,
                actor=administrator,
            )
            ids.append(op.pk)
        except Exception as exc:
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [Thread(target=runner) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not any(thread.is_alive() for thread in threads)
    assert not errors
    assert len(ids) == 2 and ids[0] == ids[1]
    assert PrivacyRequest.objects.count() == 1
