import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User

pytestmark = pytest.mark.django_db

PASSWORD = "A-strong-test-password-329"


def create_user(email="user@example.com", *, is_staff=False, is_superuser=False):
    return User.objects.create_user(
        email=email,
        password=PASSWORD,
        is_staff=is_staff,
        is_superuser=is_superuser,
    )


def bearer_client(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


@override_settings(ALLOW_PUBLIC_REGISTRATION=True)
def test_register_validates_password_and_restricts_privilege(client):
    invalid = client.post(
        reverse("auth-register"),
        {"email": "abc@example.com", "password": "123", "is_superuser": True},
    )
    assert invalid.status_code == 400

    response = client.post(
        reverse("auth-register"),
        {
            "email": "Alice@Example.Com",
            "password": PASSWORD,
            "first_name": "Alice",
            "is_staff": True,
            "is_superuser": True,
        },
    )
    assert response.status_code == 201, response.content
    created = User.objects.get(email="alice@example.com")
    assert response.data["email"] == "alice@example.com"
    assert "password" not in response.data
    assert not created.is_staff
    assert not created.is_superuser


def test_registration_disabled_by_default(client):
    response = client.post(reverse("auth-register"), {"email": "x@example.com", "password": PASSWORD})
    assert response.status_code == 403


def test_login_and_profile_roundtrip(client):
    user = create_user()
    login = client.post(reverse("auth-login"), {"email": "USER@EXAMPLE.COM", "password": PASSWORD})
    assert login.status_code == 200, login.content
    assert "access" in login.data and "refresh" in login.data
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    profile = api.get(reverse("users-me"))
    assert profile.status_code == 200
    assert profile.data["id"] == str(user.id)
    updated = api.patch(reverse("users-me"), {"first_name": "Alice", "is_staff": True})
    assert updated.status_code == 200
    user.refresh_from_db()
    assert user.first_name == "Alice" and not user.is_staff


def test_login_does_not_expose_identity(client):
    create_user()
    wrong_password = client.post(reverse("auth-login"), {"email": "user@example.com", "password": "wrong"})
    missing_user = client.post(reverse("auth-login"), {"email": "absent@example.com", "password": "wrong"})
    assert wrong_password.status_code == 401
    assert missing_user.status_code == 401
    assert wrong_password.data == missing_user.data


def test_inactive_user_cannot_login_or_use_tokens(client):
    user = create_user()
    user.is_active = False
    user.save(update_fields=["is_active"])
    assert client.post(reverse("auth-login"), {"email": user.email, "password": PASSWORD}).status_code == 401
    assert bearer_client(user).get(reverse("users-me")).status_code == 401


def test_anonymous_cannot_read_profile_or_admin(client):
    assert client.get(reverse("users-me")).status_code in {401, 403}
    assert client.get(reverse("admin-users-list")).status_code in {401, 403}


def test_admin_user_operations_protect_against_idor_and_privilege_escalation():
    customer = create_user()
    other = create_user("other@example.com")
    staff = create_user("staff@example.com", is_staff=True)
    superuser = create_user("admin@example.com", is_staff=True, is_superuser=True)

    for member in [customer, staff]:
        api = bearer_client(member)
        assert api.get(reverse("admin-users-list")).status_code == 403
        assert api.get(reverse("admin-users-detail", kwargs={"pk": other.pk})).status_code == 403
        assert api.patch(
            reverse("admin-users-detail", kwargs={"pk": other.pk}), {"is_active": False}
        ).status_code == 403

    admin = bearer_client(superuser)
    assert admin.get(reverse("admin-users-list")).status_code == 200
    assert admin.patch(
        reverse("admin-users-detail", kwargs={"pk": customer.pk}),
        {"is_staff": True, "is_superuser": True, "is_active": False},
    ).status_code == 200
    customer.refresh_from_db()
    assert not customer.is_active and not customer.is_staff and not customer.is_superuser
    response = admin.patch(reverse("admin-users-detail", kwargs={"pk": superuser.pk}), {"is_active": False})
    assert response.status_code == 400


def test_logout_revokes_refresh_token(client):
    user = create_user()
    login = client.post(reverse("auth-login"), {"email": user.email, "password": PASSWORD})
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    assert api.post(reverse("auth-logout"), {"refresh": login.data["refresh"]}).status_code == 204
    assert client.post(reverse("auth-refresh"), {"refresh": login.data["refresh"]}).status_code == 401


def test_cannot_revoke_someone_elses_refresh_token(client):
    one = create_user()
    two = create_user("two@example.com")
    refresh = str(RefreshToken.for_user(one))
    response = bearer_client(two).post(reverse("auth-logout"), {"refresh": refresh})
    assert response.status_code == 400
    assert client.post(reverse("auth-refresh"), {"refresh": refresh}).status_code == 200


def test_change_password_invalidates_existing_tokens(client):
    user = create_user()
    login = client.post(reverse("auth-login"), {"email": user.email, "password": PASSWORD})
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    response = api.post(
        reverse("users-change-password"),
        {"current_password": PASSWORD, "new_password": "Stronger-New-Password-783"},
    )
    assert response.status_code == 204, response.content
    assert api.get(reverse("users-me")).status_code == 401
    assert client.post(reverse("auth-refresh"), {"refresh": login.data["refresh"]}).status_code == 401
    assert client.post(
        reverse("auth-login"),
        {"email": user.email, "password": "Stronger-New-Password-783"},
    ).status_code == 200
