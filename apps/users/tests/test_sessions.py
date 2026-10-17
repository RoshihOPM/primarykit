"""Session ownership, revocation, rotation, privacy and lifecycle regressions (issue #48)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.core.management import call_command
from django.db import connection
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import DeviceSession, User

pytestmark = pytest.mark.django_db

PASSWORD = "A-strong-test-password-329"


def new_user(email="one@example.com", **kwargs):
    return User.objects.create_user(
        email=email, password=PASSWORD, email_verified=True, **kwargs
    )


def login(client, user, *, agent="Mozilla/5.0 (Windows NT 10.0) Chrome/125.0 Safari/537.36"):
    response = client.post(
        reverse("auth-login"),
        {"email": user.email, "password": PASSWORD},
        HTTP_USER_AGENT=agent,
    )
    assert response.status_code == 200, response.content
    return response.data


def api(access):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def test_device_session_list_current_flag_and_safe_metadata(client):
    member = new_user()
    first = login(client, member)
    second = login(
        client,
        member,
        agent='<script>alert("x")</script> Mozilla/5.0 (iPhone) '
        "AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1",
    )
    items = api(second["access"]).get(reverse("users-sessions"))
    assert items.status_code == 200
    assert items.data["count"] == 2
    entries = items.data["results"]
    assert set(entries[0]) == {
        "id", "browser", "os", "device_type", "created_at",
        "last_seen_at", "expires_at", "is_current",
    }
    assert [e["is_current"] for e in entries] == [True, False]
    assert entries[0]["browser"] == "Safari"
    assert entries[0]["os"] == "iOS"
    assert entries[0]["device_type"] == "mobile"
    assert all("script" not in str(e).lower() for e in entries)
    assert DeviceSession.objects.filter(user=member).count() == 2
    assert api(first["access"]).get(reverse("users-sessions")).data["count"] == 2


def test_revoke_one_blocks_only_its_refresh_but_access_lags(client):
    member = new_user()
    first, second = login(client, member), login(client, member)
    first_id = RefreshToken(first["refresh"])["sid"]
    owner_api = api(second["access"])
    url = reverse("users-sessions-revoke", kwargs={"session_id": first_id})
    assert owner_api.delete(url).status_code == 204
    assert owner_api.delete(url).status_code == 204
    assert client.post(reverse("auth-refresh"), {"refresh": first["refresh"]}).status_code == 401
    assert client.post(reverse("auth-refresh"), {"refresh": second["refresh"]}).status_code == 200
    assert api(first["access"]).get(reverse("users-me")).status_code == 200
    assert owner_api.get(reverse("users-sessions")).data["count"] == 1


def test_other_user_and_staff_cannot_read_or_revoke_sessions(client):
    victim = new_user()
    attacker = new_user("attacker@example.com", is_staff=True, is_superuser=True)
    victim_tokens = login(client, victim)
    attacker_tokens = login(client, attacker)
    victim_sid = RefreshToken(victim_tokens["refresh"])["sid"]
    attacker_api = api(attacker_tokens["access"])
    sessions = attacker_api.get(reverse("users-sessions"))
    assert sessions.status_code == 200
    assert sessions.data["count"] == 1
    assert (
        attacker_api.delete(
            reverse("users-sessions-revoke", kwargs={"session_id": victim_sid})
        ).status_code
        == 404
    )
    assert client.post(reverse("auth-refresh"), {"refresh": victim_tokens["refresh"]}).status_code == 200


def test_anonymous_denied_on_all_session_endpoints(client):
    for name in ("users-sessions", "users-sessions-revoke-all"):
        url = reverse(name)
        assert client.get(url).status_code in {401, 403}
        assert client.post(url).status_code in {401, 403}
    sid = "00000000-0000-0000-0000-000000000001"
    assert client.delete(
        reverse("users-sessions-revoke", kwargs={"session_id": sid})
    ).status_code in {401, 403}


def test_revoke_all_is_owner_scoped_and_new_login_is_allowed(client):
    first_user = new_user()
    second_user = new_user("second@example.com")
    tokens1, tokens2 = login(client, first_user), login(client, first_user)
    other = login(client, second_user)
    response = api(tokens1["access"]).post(reverse("users-sessions-revoke-all"))
    assert response.status_code == 204
    assert DeviceSession.objects.filter(user=first_user, revoked_at__isnull=True).count() == 0
    assert DeviceSession.objects.filter(user=second_user, revoked_at__isnull=True).count() == 1
    for token in (tokens1, tokens2):
        assert client.post(reverse("auth-refresh"), {"refresh": token["refresh"]}).status_code == 401
    assert client.post(reverse("auth-refresh"), {"refresh": other["refresh"]}).status_code == 200
    new = login(client, first_user)
    assert client.post(reverse("auth-refresh"), {"refresh": new["refresh"]}).status_code == 200


def test_refresh_rotates_and_retains_session_id(client):
    member = new_user()
    tokens = login(client, member)
    sid = RefreshToken(tokens["refresh"])["sid"]
    response = client.post(reverse("auth-refresh"), {"refresh": tokens["refresh"]})
    assert response.status_code == 200, response.content
    assert RefreshToken(response.data["refresh"])["sid"] == sid
    assert client.post(reverse("auth-refresh"), {"refresh": tokens["refresh"]}).status_code == 401
    session = DeviceSession.objects.get(pk=sid)
    assert session.last_seen_at >= session.created_at
    assert session.expires_at == datetime.fromtimestamp(
        RefreshToken(response.data["refresh"])["exp"], tz=dt_timezone.utc
    )
    assert api(response.data["access"]).get(reverse("users-sessions")).data["results"][0]["is_current"]


def test_legacy_refresh_without_session_is_rejected(client):
    member = new_user()
    refresh = str(RefreshToken.for_user(member))
    assert client.post(reverse("auth-refresh"), {"refresh": refresh}).status_code == 401


def test_expired_or_revoked_session_cannot_refresh(client):
    member = new_user()
    tokens = login(client, member)
    DeviceSession.objects.filter(user=member).update(expires_at=timezone.now() - timedelta(seconds=1))
    assert client.post(reverse("auth-refresh"), {"refresh": tokens["refresh"]}).status_code == 401
    assert api(tokens["access"]).get(reverse("users-sessions")).data["count"] == 0


def test_logout_blacklists_refresh_and_retires_session(client):
    member = new_user()
    tokens = login(client, member)
    response = api(tokens["access"]).post(
        reverse("auth-logout"), {"refresh": tokens["refresh"]}
    )
    assert response.status_code == 204
    assert DeviceSession.objects.get(user=member).revoked_at is not None
    assert client.post(reverse("auth-refresh"), {"refresh": tokens["refresh"]}).status_code == 401


def test_change_password_revokes_all_sessions(client):
    member = new_user()
    t1, t2 = login(client, member), login(client, member)
    response = api(t1["access"]).post(
        reverse("users-change-password"),
        {"current_password": PASSWORD, "new_password": "Different-very-strong-password-981"},
    )
    assert response.status_code == 204
    assert DeviceSession.objects.filter(user=member, revoked_at__isnull=True).count() == 0
    assert client.post(reverse("auth-refresh"), {"refresh": t1["refresh"]}).status_code == 401
    assert client.post(reverse("auth-refresh"), {"refresh": t2["refresh"]}).status_code == 401


def test_deleting_account_cascades_to_sessions(client):
    member = new_user()
    login(client, member)
    assert DeviceSession.objects.count() == 1
    member.delete()
    assert DeviceSession.objects.count() == 0


def test_purge_removes_only_old_ended_sessions(client):
    member = new_user()
    one, two, three = login(client, member), login(client, member), login(client, member)
    ids = [RefreshToken(token["refresh"])["sid"] for token in (one, two, three)]
    past = timezone.now() - timedelta(days=40)
    DeviceSession.objects.filter(pk=ids[0]).update(revoked_at=past)
    DeviceSession.objects.filter(pk=ids[1]).update(expires_at=past)
    call_command("purge_device_sessions", days=30)
    assert list(DeviceSession.objects.values_list("pk", flat=True)) == [
        DeviceSession.objects.get(pk=ids[2]).pk
    ]


@pytest.mark.django_db(transaction=True)
def test_parallel_refresh_has_one_winner(client):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row locking required")
    member = new_user()
    tokens = login(client, member)

    def refresh():
        return APIClient().post(
            reverse("auth-refresh"), {"refresh": tokens["refresh"]}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: refresh(), range(2)))
    assert sorted(results) == [200, 401]


@pytest.mark.django_db(transaction=True)
def test_revoke_all_wins_against_inflight_refresh(client):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row locking required")
    member = new_user()
    tokens = login(client, member)

    def refresh():
        response = APIClient().post(
            reverse("auth-refresh"), {"refresh": tokens["refresh"]}
        )
        return response.data.get("refresh") if response.status_code == 200 else None

    def revoke():
        return api(tokens["access"]).post(reverse("users-sessions-revoke-all")).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        future_refresh = pool.submit(refresh)
        future_revoke = pool.submit(revoke)
        rotated = future_refresh.result()
        assert future_revoke.result() == 204
    if rotated:
        assert client.post(reverse("auth-refresh"), {"refresh": rotated}).status_code == 401
    assert DeviceSession.objects.filter(user=member, revoked_at__isnull=True).count() == 0
