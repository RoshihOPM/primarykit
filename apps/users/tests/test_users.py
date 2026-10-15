import pytest

from apps.users.models import User


@pytest.mark.django_db
def test_create_user_with_email():
    user = User.objects.create_user(email="Dev@Example.COM", password="test-password-123")
    assert user.email == "Dev@example.com"
    assert user.check_password("test-password-123")
    assert not user.is_staff


@pytest.mark.django_db
def test_create_superuser():
    user = User.objects.create_superuser(email="admin@example.com", password="test-password-123")
    assert user.is_staff
    assert user.is_superuser


@pytest.mark.django_db
def test_email_is_unique():
    User.objects.create_user(email="same@example.com", password="test-password-123")
    with pytest.raises(Exception):
        User.objects.create_user(email="same@example.com", password="test-password-123")
