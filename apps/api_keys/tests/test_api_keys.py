import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection, connections
from django.test import RequestFactory, override_settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from apps.api_keys.authentication import scoped_api_key_authentication
from apps.api_keys.models import ApiKey
from apps.api_keys.services import issue_api_key, revoke_api_key, rotate_api_key, verify_api_key
from apps.users.models import User

pytestmark = pytest.mark.django_db
POLICIES = {"reports.read": "auth.view_user", "reports.write": "auth.change_user"}


def user(email="owner@example.test", *, superuser=False):
    return User.objects.create_user(
        email=email,
        password="strong-test-password",
        email_verified=True,
        is_staff=superuser,
        is_superuser=superuser,
    )


def expires():
    return timezone.now() + timedelta(days=7)


@override_settings(API_KEY_SCOPE_PERMISSIONS=POLICIES)
def test_issue_verify_and_no_plaintext_persistence():
    owner = user(superuser=True)
    key, token = issue_api_key(
        actor=owner, name="integration", scopes=("reports.read",), expires_at=expires()
    )
    assert token.startswith(f"pk_{key.pk.hex}.")
    assert token not in repr(key) and token not in str(key)
    assert (
        ApiKey.objects.get(pk=key.pk).secret_digest
        == hashlib.sha256(token.split(".")[1].encode("ascii")).hexdigest()
    )
    assert verify_api_key(token, required_scope="reports.read")[0].pk == owner.pk
    with pytest.raises(AuthenticationFailed):
        verify_api_key(token, required_scope="reports.write")
    with pytest.raises(AuthenticationFailed):
        verify_api_key(token + "x", required_scope="reports.read")


@override_settings(API_KEY_SCOPE_PERMISSIONS=POLICIES)
def test_unprivileged_user_cannot_issue_arbitrary_scopes():
    normal = user()
    with pytest.raises(PermissionDenied):
        issue_api_key(actor=normal, name="no", scopes=("reports.read",), expires_at=expires())
    admin = user("admin@example.test", superuser=True)
    with pytest.raises(PermissionDenied):
        issue_api_key(actor=admin, name="no", scopes=("admin",), expires_at=expires())
    with pytest.raises(ValidationError):
        issue_api_key(
            actor=admin,
            name="expired",
            scopes=("reports.read",),
            expires_at=timezone.now() - timedelta(seconds=1),
        )


@override_settings(API_KEY_SCOPE_PERMISSIONS=POLICIES)
def test_revoke_owner_only_and_rotation():
    owner = user(superuser=True)
    other = user("other@example.test", superuser=True)
    key, token = issue_api_key(
        actor=owner, name="service", scopes=("reports.read",), expires_at=expires()
    )
    with pytest.raises(PermissionDenied):
        revoke_api_key(actor=other, key_id=key.pk)
    rotated, next_token = rotate_api_key(actor=owner, key_id=key.pk, expires_at=expires())
    with pytest.raises(AuthenticationFailed):
        verify_api_key(token, required_scope="reports.read")
    assert verify_api_key(next_token, required_scope="reports.read")[1].pk == rotated.pk
    revoke_api_key(actor=owner, key_id=rotated.pk)
    with pytest.raises(AuthenticationFailed):
        verify_api_key(next_token, required_scope="reports.read")
    with pytest.raises(PermissionDenied):
        rotate_api_key(actor=owner, key_id=key.pk, expires_at=expires())


@override_settings(API_KEY_SCOPE_PERMISSIONS=POLICIES)
def test_scoped_authentication_opt_in_and_revocation_on_owner_disable():
    owner = user(superuser=True)
    key, token = issue_api_key(
        actor=owner, name="service", scopes=("reports.read",), expires_at=expires()
    )
    authentication = scoped_api_key_authentication("reports.read")()
    factory = RequestFactory()
    assert authentication.authenticate(factory.get("/x")) is None
    returned_owner, auth = authentication.authenticate(
        factory.get("/x", HTTP_AUTHORIZATION=f"ApiKey {token}")
    )
    assert returned_owner.pk == owner.pk and auth.pk == key.pk
    owner.is_active = False
    owner.save(update_fields=["is_active"])
    with pytest.raises(AuthenticationFailed):
        authentication.authenticate(factory.get("/x", HTTP_AUTHORIZATION=f"ApiKey {token}"))


@override_settings(API_KEY_SCOPE_PERMISSIONS=POLICIES)
def test_scope_policy_change_fails_closed():
    owner = user(superuser=True)
    key, token = issue_api_key(
        actor=owner, name="service", scopes=("reports.read",), expires_at=expires()
    )
    with override_settings(API_KEY_SCOPE_PERMISSIONS={}):
        with pytest.raises(AuthenticationFailed):
            verify_api_key(token, required_scope="reports.read")
    key.expires_at = timezone.now() - timedelta(minutes=1)
    key.save(update_fields=["expires_at"])
    with pytest.raises(AuthenticationFailed):
        verify_api_key(token, required_scope="reports.read")


@override_settings(API_KEY_SCOPE_PERMISSIONS=POLICIES)
def test_issue_is_bound_to_the_actor_not_an_owner_id():
    actor = user(superuser=True)
    other = user("unrelated@example.test", superuser=True)
    record, _token = issue_api_key(
        actor=actor, name="restricted", scopes=("reports.read",), expires_at=expires()
    )
    assert record.owner_id == actor.pk
    assert not ApiKey.objects.filter(pk=record.pk, owner=other).exists()
    with pytest.raises(TypeError):
        issue_api_key(
            actor=actor,
            owner=other,
            name="forbidden",
            scopes=("reports.read",),
            expires_at=expires(),
        )


@pytest.mark.django_db(transaction=True)
@override_settings(API_KEY_SCOPE_PERMISSIONS=POLICIES)
def test_concurrent_rotations_have_single_winner_on_postgresql():
    if connection.vendor != "postgresql":
        pytest.skip("Row locking requires PostgreSQL")
    owner = user(superuser=True)
    original, _token = issue_api_key(
        actor=owner, name="worker", scopes=("reports.read",), expires_at=expires()
    )
    gate = Barrier(2)

    def rotate_once():
        close_old_connections()
        try:
            own_user = User.objects.get(pk=owner.pk)
            gate.wait(timeout=15)
            try:
                new_record, _new_token = rotate_api_key(
                    actor=own_user, key_id=original.pk, expires_at=expires()
                )
            except PermissionDenied:
                return None
            return new_record.pk
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _index: rotate_once(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert ApiKey.objects.filter(owner=owner, revoked_at__isnull=True).count() == 1
