from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group, Permission
from django.test import override_settings
from django.urls import reverse
from rest_framework.generics import GenericAPIView
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.rbac.permissions import (
    HasRequiredPermissions,
    IsOwnerOrGlobalPermission,
    OwnerScopedQuerysetMixin,
)
from apps.users.models import User

pytestmark = pytest.mark.django_db

PERMISSION_CODE = "auth.view_group"


def user(email, **kwargs):
    return User.objects.create_user(email=email, password="a-strong-password-123", **kwargs)


def as_user(member):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(member).access_token}")
    return client


@pytest.fixture
def identities():
    return (
        user("admin@example.com", is_staff=True, is_superuser=True),
        user("regular@example.com"),
        user("staff@example.com", is_staff=True),
        user("another@example.com"),
    )


def test_no_rbac_admin_access_for_non_superusers(identities):
    _, normal, staff, _ = identities
    for actor in (normal, staff):
        client = as_user(actor)
        assert client.get(reverse("rbac-roles-list")).status_code == 403
        assert client.post(reverse("rbac-roles-list"), {"name": "Admin"}).status_code == 403
        assert client.get(reverse("rbac-permissions-list")).status_code == 403
        assert (
            client.put(
                reverse("rbac-user-roles", kwargs={"user_id": normal.pk}), {"role_ids": []}
            ).status_code
            == 403
        )


@override_settings(RBAC_ASSIGNABLE_PERMISSIONS=[PERMISSION_CODE])
def test_role_creation_assignment_and_permissions(identities):
    admin, normal, _, _ = identities
    client = as_user(admin)
    permission = Permission.objects.get(content_type__app_label="auth", codename="view_group")
    response = client.post(
        reverse("rbac-roles-list"),
        {"name": "Reader", "permission_codes": [PERMISSION_CODE]},
        format="json",
    )
    assert response.status_code == 201, response.data
    role_id = response.data["id"]
    role = Group.objects.get(pk=role_id)
    assert list(role.permissions.all()) == [permission]

    assign = client.put(
        reverse("rbac-user-roles", kwargs={"user_id": normal.pk}),
        {"role_ids": [role_id]},
        format="json",
    )
    assert assign.status_code == 204
    normal.refresh_from_db()
    assert normal.has_perm(PERMISSION_CODE)
    assert (
        as_user(normal).get(reverse("rbac-roles-detail", kwargs={"pk": role_id})).status_code == 403
    )
    assert client.get(reverse("rbac-user-roles", kwargs={"user_id": normal.pk})).data["roles"] == [
        {"id": role_id, "name": "Reader"}
    ]
    assert client.delete(reverse("rbac-roles-detail", kwargs={"pk": role_id})).status_code == 400


@override_settings(RBAC_ASSIGNABLE_PERMISSIONS=[])
def test_role_permissions_default_deny_and_mass_assignment(identities):
    admin, _, _, _ = identities
    client = as_user(admin)
    response = client.post(
        reverse("rbac-roles-list"),
        {"name": "Escalator", "permission_codes": ["auth.add_group"]},
        format="json",
    )
    assert response.status_code == 400
    assert not Group.objects.filter(name="Escalator").exists()
    result = client.post(
        reverse("rbac-roles-list"),
        {"name": "Safe", "is_superuser": True},
        format="json",
    )
    assert result.status_code == 201
    role = Group.objects.get(name="Safe")
    assert not role.permissions.exists()
    assert client.get(reverse("rbac-permissions-list")).data["results"] == []


def test_missing_role_and_atomic_replacement(identities):
    admin, normal, _, _ = identities
    client = as_user(admin)
    first = Group.objects.create(name="first")
    second = Group.objects.create(name="second")
    assert (
        client.put(
            reverse("rbac-user-roles", kwargs={"user_id": normal.pk}),
            {"role_ids": [first.pk, second.pk]},
            format="json",
        ).status_code
        == 204
    )
    invalid = client.put(
        reverse("rbac-user-roles", kwargs={"user_id": normal.pk}),
        {"role_ids": [first.pk, 999999999]},
        format="json",
    )
    assert invalid.status_code == 400
    normal.refresh_from_db()
    assert set(normal.groups.values_list("pk", flat=True)) == {first.pk, second.pk}
    assert (
        client.put(
            reverse("rbac-user-roles", kwargs={"user_id": normal.pk}),
            {"role_ids": [second.pk]},
            format="json",
        ).status_code
        == 204
    )
    assert list(normal.groups.values_list("pk", flat=True)) == [second.pk]


def test_permission_mixin_denies_unconfigured_views(identities):
    _, normal, _, _ = identities
    request = SimpleNamespace(user=normal, method="GET")
    assert not HasRequiredPermissions().has_permission(request, SimpleNamespace())
    role = Group.objects.create(name="ReadGroup")
    role.permissions.add(
        Permission.objects.get(content_type__app_label="auth", codename="view_group")
    )
    normal.groups.add(role)
    view = SimpleNamespace(required_permissions={"GET": [PERMISSION_CODE]})
    assert HasRequiredPermissions().has_permission(request, view)
    assert not HasRequiredPermissions().has_permission(
        SimpleNamespace(user=normal, method="DELETE"), view
    )


def test_owner_queryset_and_object_permissions(identities):
    admin, normal, staff, another = identities

    class OwnedUsersView(OwnerScopedQuerysetMixin, GenericAPIView):
        queryset = User.objects.all()
        owner_lookup = "pk"
        owner_attribute = "pk"
        global_scope_permissions = {"GET": PERMISSION_CODE}

    view = OwnedUsersView()
    view.request = SimpleNamespace(user=normal, method="GET")
    assert list(view.get_queryset()) == [normal]
    perm = IsOwnerOrGlobalPermission()
    assert perm.has_object_permission(view.request, view, normal)
    assert not perm.has_object_permission(view.request, view, another)
    role = Group.objects.create(name="read-all")
    role.permissions.add(
        Permission.objects.get(content_type__app_label="auth", codename="view_group")
    )
    staff.groups.add(role)
    view.request = SimpleNamespace(user=staff, method="GET")
    assert set(view.get_queryset()) == {admin, normal, staff, another}
    assert perm.has_object_permission(view.request, view, another)
    view.request = SimpleNamespace(user=staff, method="PATCH")
    assert list(view.get_queryset()) == [staff]
    assert not perm.has_object_permission(view.request, view, another)
