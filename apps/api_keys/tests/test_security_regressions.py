"""Regression tests for API-key authority and atomic rotation."""

from datetime import timedelta

import pytest
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.test import override_settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from apps.api_keys.models import ApiKey
from apps.api_keys.services import issue_api_key, rotate_api_key, verify_api_key
from apps.users.models import User

pytestmark = pytest.mark.django_db

POLICIES = {"reports.read": "auth.view_user"}


def owner():
    return User.objects.create_user(
        email="key-regression-owner@example.test",
        password="long-test-password-2026",
        email_verified=True,
        is_staff=True,
        is_superuser=True,
    )


def expiry():
    return timezone.now() + timedelta(days=7)


@override_settings(API_KEY_SCOPE_PERMISSIONS=POLICIES)
def test_scope_permission_revocation_invalidates_existing_credential():
    actor = owner()
    record, token = issue_api_key(
        actor=actor, name="reports", scopes=("reports.read",), expires_at=expiry()
    )
    assert verify_api_key(token, required_scope="reports.read")[1].pk == record.pk

    actor.is_superuser = False
    actor.save(update_fields=("is_superuser",))

    with pytest.raises(AuthenticationFailed):
        verify_api_key(token, required_scope="reports.read")
    # Revoking the underlying Django permission is effective without deleting the key.
    assert ApiKey.objects.filter(pk=record.pk, revoked_at__isnull=True).exists()


@pytest.mark.parametrize(
    "scopes",
    [
        (),
        ("reports.read", "reports.read"),
        ("reports.write",),
        ("reports.read",) * 17,
    ],
)
@override_settings(API_KEY_SCOPE_PERMISSIONS=POLICIES)
def test_invalid_scope_grants_never_persist(scopes):
    actor = owner()
    with pytest.raises(PermissionDenied):
        issue_api_key(actor=actor, name="invalid", scopes=scopes, expires_at=expiry())
    assert not ApiKey.objects.exists()


@override_settings(API_KEY_SCOPE_PERMISSIONS=POLICIES)
def test_invalid_rotation_expiry_preserves_original_key():
    actor = owner()
    original, token = issue_api_key(
        actor=actor, name="worker", scopes=("reports.read",), expires_at=expiry()
    )

    with pytest.raises(ValidationError):
        rotate_api_key(
            actor=actor,
            key_id=original.pk,
            expires_at=timezone.now() - timedelta(minutes=1),
        )

    original.refresh_from_db()
    assert original.revoked_at is None
    assert ApiKey.objects.filter(owner=actor).count() == 1
    assert verify_api_key(token, required_scope="reports.read")[1].pk == original.pk


@pytest.mark.parametrize(
    "invalid_expiry",
    [
        lambda now: now - timedelta(seconds=1),
        lambda now: now + timedelta(days=91),
        lambda now: now.replace(tzinfo=None),
    ],
)
@override_settings(API_KEY_SCOPE_PERMISSIONS=POLICIES)
def test_issue_rejects_expired_overlong_and_naive_expirations(invalid_expiry):
    actor = owner()
    with pytest.raises(ValidationError):
        issue_api_key(
            actor=actor,
            name="unsafe-expiry",
            scopes=("reports.read",),
            expires_at=invalid_expiry(timezone.now()),
        )
    assert not ApiKey.objects.exists()


@override_settings(API_KEY_SCOPE_PERMISSIONS={"reports.read": "unqualified"})
def test_invalid_scope_policy_fails_closed():
    actor = owner()
    with pytest.raises(ImproperlyConfigured):
        issue_api_key(
            actor=actor,
            name="bad-config",
            scopes=("reports.read",),
            expires_at=expiry(),
        )
    assert not ApiKey.objects.exists()
