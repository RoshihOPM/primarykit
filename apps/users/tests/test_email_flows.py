"""Email verification and password reset security regression tests."""

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User

pytestmark = pytest.mark.django_db
PASSWORD = "A-strong-test-password-329"
MAIL_ENABLED = {
    "AUTH_EMAIL_FLOWS_ENABLED": True,
    "AUTH_VERIFICATION_URL": "https://frontend.example.test/verify-email",
    "AUTH_PASSWORD_RESET_URL": "https://frontend.example.test/reset-password",
}


def user(email="member@example.com", *, verified=True):
    return User.objects.create_user(
        email=email,
        password=PASSWORD,
        email_verified=verified,
    )


def credentials_from_email(index=-1):
    assert mail.outbox
    body = mail.outbox[index].body
    link = next(word for word in body.split() if word.startswith("https://frontend.example.test/"))
    query = parse_qs(urlsplit(link).query)
    return {"uid": query["uid"][0], "token": query["token"][0]}


def auth_client(member):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(member).access_token}")
    return client


def test_flows_are_disabled_without_configuration(client):
    for name in [
        "auth-email-resend",
        "auth-email-verify",
        "auth-password-reset-request",
        "auth-password-reset-confirm",
    ]:
        assert client.post(reverse(name), {}).status_code == 503


@override_settings(ALLOW_PUBLIC_REGISTRATION=True, **MAIL_ENABLED)
def test_registration_sends_one_use_email_and_login_requires_verification(client):
    response = client.post(
        reverse("auth-register"),
        {"email": "NEW@Example.COM", "password": PASSWORD},
    )
    assert response.status_code == 201, response.content
    member = User.objects.get(email="new@example.com")
    assert not member.email_verified
    assert len(mail.outbox) == 1
    assert not member.is_staff
    assert not member.is_superuser
    assert client.post(
        reverse("auth-login"), {"email": member.email, "password": PASSWORD}
    ).status_code == 401
    assert auth_client(member).get(reverse("users-me")).status_code == 401

    tokens = credentials_from_email()
    assert client.post(reverse("auth-email-verify"), {**tokens, "is_staff": True}).status_code == 204
    member.refresh_from_db()
    assert member.email_verified
    assert client.post(reverse("auth-email-verify"), tokens).status_code == 400
    assert client.post(
        reverse("auth-login"), {"email": member.email, "password": PASSWORD}
    ).status_code == 200


@override_settings(ALLOW_PUBLIC_REGISTRATION=True, **MAIL_ENABLED)
def test_registration_fails_closed_when_mailer_cannot_send(client):
    with override_settings(
        MAILERS={"default": {"BACKEND": "django.core.mail.backends.dummy.EmailBackend"}}
    ):
        result = client.post(
            reverse("auth-register"), {"email": "undelivered@example.com", "password": PASSWORD}
        )
    assert result.status_code == 503
    assert not User.objects.filter(email="undelivered@example.com").exists()


@override_settings(**MAIL_ENABLED)
def test_verification_reissue_uses_generic_response_and_invalidates_used_token(client):
    member = user(verified=False)
    unknown = client.post(reverse("auth-email-resend"), {"email": "missing@example.com"})
    assert unknown.status_code == 202
    assert len(mail.outbox) == 0

    sent = client.post(reverse("auth-email-resend"), {"email": "MEMBER@EXAMPLE.COM"})
    assert sent.status_code == 202
    assert sent.data == unknown.data
    assert len(mail.outbox) == 1

    tokens = credentials_from_email()
    assert client.post(reverse("auth-email-verify"), {"uid": tokens["uid"], "token": "bad"}).status_code == 400
    assert client.post(reverse("auth-email-verify"), tokens).status_code == 204
    member.refresh_from_db()
    assert member.email_verified
    assert client.post(reverse("auth-email-verify"), tokens).status_code == 400


@override_settings(**MAIL_ENABLED)
def test_verification_link_cannot_be_used_for_another_account(client):
    first = user("one@example.com", verified=False)
    user("two@example.com", verified=False)
    client.post(reverse("auth-email-resend"), {"email": first.email})
    original = credentials_from_email()
    other = user("three@example.com", verified=False)
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    other_uid = urlsafe_base64_encode(force_bytes(other.pk))
    assert client.post(
        reverse("auth-email-verify"), {"uid": other_uid, "token": original["token"]}
    ).status_code == 400


@override_settings(**MAIL_ENABLED)
def test_password_reset_is_single_use_and_revokes_existing_tokens(client):
    member = user()
    login = client.post(reverse("auth-login"), {"email": member.email, "password": PASSWORD})
    assert login.status_code == 200
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    missing = client.post(reverse("auth-password-reset-request"), {"email": "none@example.com"})
    existing = client.post(reverse("auth-password-reset-request"), {"email": "MEMBER@EXAMPLE.COM"})
    assert missing.status_code == existing.status_code == 202
    assert missing.data == existing.data
    assert len(mail.outbox) == 1

    fields = credentials_from_email()
    assert client.post(
        reverse("auth-password-reset-confirm"), {**fields, "new_password": "short"}
    ).status_code == 400
    done = client.post(
        reverse("auth-password-reset-confirm"),
        {**fields, "new_password": "New-password-for-testing-632"},
    )
    assert done.status_code == 204, done.content
    assert client.post(
        reverse("auth-password-reset-confirm"),
        {**fields, "new_password": "another-new-password-781"},
    ).status_code == 400
    assert api.get(reverse("users-me")).status_code == 401
    assert client.post(reverse("auth-refresh"), {"refresh": login.data["refresh"]}).status_code == 401
    assert client.post(reverse("auth-login"), {"email": member.email, "password": PASSWORD}).status_code == 401
    assert client.post(
        reverse("auth-login"),
        {"email": member.email, "password": "New-password-for-testing-632"},
    ).status_code == 200


@override_settings(**MAIL_ENABLED)
def test_password_reset_does_not_verify_an_unverified_email(client):
    member = user(verified=False)
    client.post(reverse("auth-password-reset-request"), {"email": member.email})
    fields = credentials_from_email()
    assert client.post(
        reverse("auth-password-reset-confirm"),
        {**fields, "new_password": "Different-long-password-931"},
    ).status_code == 204
    member.refresh_from_db()
    assert not member.email_verified
    assert client.post(
        reverse("auth-login"), {"email": member.email, "password": "Different-long-password-931"}
    ).status_code == 401


@override_settings(**MAIL_ENABLED, PASSWORD_RESET_TIMEOUT=3600)
def test_password_reset_token_expires(client):
    member = user()
    token = default_token_generator.make_token(member)
    now = timezone.now()
    with patch.object(default_token_generator, "_now", return_value=now + timedelta(hours=2)):
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        result = client.post(
            reverse("auth-password-reset-confirm"),
            {
                "uid": urlsafe_base64_encode(force_bytes(member.pk)),
                "token": token,
                "new_password": "New-password-for-testing-632",
            },
        )
    assert result.status_code == 400
