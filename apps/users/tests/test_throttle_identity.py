"""Anonymous throttle identity must not be selectable by the caller."""

from types import SimpleNamespace

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.test import override_settings
from django.urls import reverse

from apps.users import throttles
from apps.users.throttles import AccountRateThrottle


def _hops(count):
    return override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "NUM_PROXIES": count})


def _request(remote="198.51.100.7", forwarded=None):
    meta = {"REMOTE_ADDR": remote}
    if forwarded is not None:
        meta["HTTP_X_FORWARDED_FOR"] = forwarded
    return SimpleNamespace(META=meta, user=AnonymousUser())


def test_default_trusts_no_proxy_hops():
    assert settings.REST_FRAMEWORK["NUM_PROXIES"] == 0
    assert throttles.client_ident(_request(forwarded="203.0.113.9")) == "198.51.100.7"
    assert throttles.client_ident(_request()) == "198.51.100.7"


def test_unset_hop_count_never_means_trust_the_header():
    with _hops(None):
        assert throttles.client_ident(_request(forwarded="203.0.113.9")) == "198.51.100.7"


@pytest.mark.parametrize(
    ("hops", "forwarded", "expected"),
    [
        (1, "203.0.113.9", "203.0.113.9"),
        # Everything left of the trusted hop is client-supplied and ignored.
        (1, "10.9.9.9, 203.0.113.9", "203.0.113.9"),
        (2, "10.9.9.9, 203.0.113.9, 192.0.2.1", "203.0.113.9"),
        (1, " 2001:DB8::1 ", "2001:db8::1"),
        # Fail closed to the directly connected peer: header shorter than the
        # trusted chain, absent, empty or not an IP address.
        (2, "203.0.113.9", "198.51.100.7"),
        (3, "10.9.9.9, 203.0.113.9", "198.51.100.7"),
        (1, None, "198.51.100.7"),
        (1, "", "198.51.100.7"),
        (1, "10.9.9.9, attacker-chosen-bucket", "198.51.100.7"),
        (1, "203.0.113.9:4711", "198.51.100.7"),
        (2, "203.0.113.9, , 192.0.2.1", "198.51.100.7"),
    ],
)
def test_trusted_hop_selection_and_fail_closed_fallback(hops, forwarded, expected):
    with _hops(hops):
        assert throttles.client_ident(_request(forwarded=forwarded)) == expected


def test_local_throttle_uses_the_same_identity_helper():
    with _hops(1):
        assert AccountRateThrottle().get_ident(_request(forwarded="1.1.1.1, 203.0.113.9")) == (
            "203.0.113.9"
        )
    with _hops(2):
        assert AccountRateThrottle().get_ident(_request(forwarded="203.0.113.9")) == "198.51.100.7"


@pytest.mark.django_db
def test_rotating_forwarded_header_cannot_bypass_login_limit(client):
    statuses = [
        client.post(
            reverse("auth-login"),
            {"email": "absent@example.com", "password": "wrong"},
            HTTP_X_FORWARDED_FOR=f"203.0.113.{attempt}",
        ).status_code
        for attempt in range(7)
    ]
    assert statuses == [401] * 5 + [429] * 2


@pytest.mark.django_db
def test_one_trusted_hop_separates_clients_behind_the_proxy(client):
    def attempt(address):
        return client.post(
            reverse("auth-login"),
            {"email": "absent@example.com", "password": "wrong"},
            HTTP_X_FORWARDED_FOR=f"10.66.66.66, {address}",
        ).status_code

    with _hops(1):
        assert [attempt("203.0.113.1") for _ in range(6)] == [401] * 5 + [429]
        assert attempt("203.0.113.2") == 401
