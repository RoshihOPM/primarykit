import pytest
from django.db import NotSupportedError, connection

from apps.search.services import search_queryset
from apps.users.models import User


def _search(queryset, **options):
    return search_queryset(
        queryset,
        scope_filters={"email": "owner@example.test"},
        text="needle",
        fields=("first_name",),
        **options,
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"scope_filters": {}},
        {"text": ""},
        {"text": "x" * 201},
        {"fields": ("password", "email__contains")},
        {"fields": ("last_login",)},
        {"fields": ("first_name", "first_name")},
        {"limit": 0},
        {"limit": 101},
    ],
)
def test_invalid_input_rejected_before_database(kwargs):
    values = {
        "scope_filters": {"email": "owner@example.test"},
        "text": "needle",
        "fields": ("first_name",),
        "limit": 25,
    }
    values.update(kwargs)
    with pytest.raises(ValueError):
        search_queryset(User.objects.all(), **values)


def test_no_sqlite_fallback():
    if connection.vendor == "postgresql":
        pytest.skip("PostgreSQL integration tested below")
    with pytest.raises(NotSupportedError):
        _search(User.objects.all())


@pytest.mark.django_db
def test_search_respects_authorized_querysets_and_owner_scope():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL-only integration")
    owner = User.objects.create_user(email="owner@example.test", password="test-password", first_name="needle")
    other = User.objects.create_user(email="other@example.test", password="test-password", first_name="needle")
    authorized = User.objects.filter(pk__in=[owner.pk, other.pk])
    found = list(_search(authorized))
    assert [user.pk for user in found] == [owner.pk]
    found = list(_search(User.objects.filter(pk=other.pk)))
    assert found == []
