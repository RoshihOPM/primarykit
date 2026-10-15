import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.core.audit import record_audit_event
from apps.users.models import User

pytestmark = pytest.mark.django_db


def make_user(*, superuser=False, name="user"):
    return User.objects.create_user(
        email=f"{name}@example.com",
        password="strong-password-1234",
        email_verified=True,
        is_staff=superuser,
        is_superuser=superuser,
    )


def api_for(user):
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return api


def test_explicit_record_and_immutability():
    member = make_user()
    event = record_event(
        actor=member,
        action="users.profile.updated",
        target_type="users.User",
        target_id=member.pk,
        changes={"first_name": {"before": "", "after": "Alice"}},
    )
    assert event.actor_id == member.pk
    assert event.changes["first_name"]["after"] == "Alice"
    event.action = "altered"
    with pytest.raises(ValidationError):
        event.save()
    with pytest.raises(ValidationError):
        event.delete()
    with pytest.raises(ValidationError):
        AuditEvent.objects.update(action="altered")
    with pytest.raises(ValidationError):
        AuditEvent.objects.all().delete()
    assert AuditEvent.objects.get(pk=event.pk).action == "users.profile.updated"


@pytest.mark.parametrize(
    "changes",
    [
        {"password": "secret"},
        {"nested": {"refresh_token": "secret"}},
        {"headers": [{"Authorization": "Bearer SECRET"}]},
        {"unsafe": object()},
        {"huge": "a" * 501},
    ],
)
def test_reject_unsafe_snapshots(changes):
    with pytest.raises(ValueError):
        record_event(
            action="users.profile.updated", target_type="users.User", target_id=1, changes=changes
        )
    assert AuditEvent.objects.count() == 0


def test_rollback_of_audited_operation():
    member = make_user()
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            member.first_name = "changed"
            member.save(update_fields=["first_name"])
            record_audit_event(
                actor=member,
                action="users.profile.updated",
                target_type="users.User",
                target_id=member.pk,
                changes={"first_name": {"before": "", "after": "changed"}},
            )
            raise RuntimeError("rollback")
    member.refresh_from_db()
    assert member.first_name == ""
    assert AuditEvent.objects.count() == 0


def test_actor_attribution_prevents_accidental_user_deletion():
    member = make_user()
    record_event(actor=member, action="users.profile.updated", target_type="users.User", target_id=member.pk)
    with pytest.raises(ProtectedError):
        member.delete()
    assert AuditEvent.objects.filter(actor=member).count() == 1


def test_admin_only_read_and_no_write_or_delete():
    member = make_user()
    admin = make_user(superuser=True, name="admin")
    event = record_event(
        actor=member,
        action="users.profile.updated",
        target_type="users.User",
        target_id=member.pk,
        changes={"first_name": {"before": "", "after": "a"}},
    )
    for method in ("get", "post"):
        api = api_for(member)
        response = getattr(api, method)(reverse("audit-events-list"))
        assert response.status_code == 403
    admin_api = api_for(admin)
    assert admin_api.get(reverse("audit-events-list")).status_code == 200
    assert admin_api.get(reverse("audit-events-detail", kwargs={"pk": event.pk})).status_code == 200
    assert (
        admin_api.delete(reverse("audit-events-detail", kwargs={"pk": event.pk})).status_code == 405
    )
    assert (
        admin_api.patch(
            reverse("audit-events-detail", kwargs={"pk": event.pk}), {"action": "hacked"}
        ).status_code
        == 405
    )
    assert admin_api.post(reverse("audit-events-list"), {"action": "hacked"}).status_code == 405
    assert AuditEvent.objects.get(pk=event.pk).action == "users.profile.updated"


def test_admin_filtered_log_does_not_expose_other_actions():
    admin = make_user(superuser=True, name="admin")
    member = make_user()
    record_event(
        actor=member, action="users.profile.updated", target_type="users.User", target_id=member.pk
    )
    record_event(actor=admin, action="rbac.role.created", target_type="auth.Group", target_id=7)
    api = api_for(admin)
    response = api.get(reverse("audit-events-list"), {"action": "users.profile.updated"})
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert str(response.data["results"][0]["actor_id"]) == str(member.pk)
    assert api.get(reverse("audit-events-list"), {"actor": "not-a-uuid"}).status_code == 400


def test_role_mutation_is_audited():
    admin = make_user(superuser=True, name="admin")
    api = api_for(admin)
    response = api.post(reverse("rbac-roles-list"), {"name": "Warehouse"}, format="json")
    assert response.status_code == 201
    role_id = response.data["id"]
    assert AuditEvent.objects.filter(action="rbac.role.created", target_id=str(role_id)).exists()
    response = api.patch(
        reverse("rbac-roles-detail", kwargs={"pk": role_id}), {"name": "Logistics"}, format="json"
    )
    assert response.status_code == 200
    assert AuditEvent.objects.filter(action="rbac.role.updated", target_id=str(role_id)).exists()
    member = make_user()
    assert (
        api.put(
            reverse("rbac-user-roles", kwargs={"user_id": member.pk}),
            {"role_ids": [role_id]},
            format="json",
        ).status_code
        == 204
    )
    assert AuditEvent.objects.filter(
        action="rbac.user.roles.changed", target_id=str(member.pk)
    ).exists()
    member.refresh_from_db()
    assert member.groups.filter(pk=role_id).exists()
    assert Group.objects.filter(pk=role_id).exists()


def test_profile_change_and_password_change_are_audited():
    member = make_user()
    api = api_for(member)
    assert api.patch(reverse("users-me"), {"first_name": "A"}, format="json").status_code == 200
    assert AuditEvent.objects.filter(action="users.profile.updated", actor=member).count() == 1
    assert (
        api.post(
            reverse("users-change-password"),
            {
                "current_password": "strong-password-1234",
                "new_password": "Different-strong-password-456",
            },
            format="json",
        ).status_code
        == 204
    )
    event = AuditEvent.objects.get(action="users.password.changed", actor=member)
    assert event.changes == {}
