"""Service-layer contacts permissions and optimistic locking invariants."""

import pytest
from rest_framework.exceptions import NotFound, ValidationError

from apps.contacts.models import Contact
from apps.contacts.services import StaleContact, edit_contact
from apps.users.models import User

pytestmark = pytest.mark.django_db


def actor(email, *, superuser=False):
    return User.objects.create_user(
        email=email,
        password="long-contact-regression-password",
        email_verified=True,
        is_staff=superuser,
        is_superuser=superuser,
    )


@pytest.mark.parametrize(
    "changes",
    [{}, {"owner_id": None}, {"version": 999}, {"created_at": None}],
)
def test_service_denies_mass_assignment_and_empty_changes(changes):
    person = actor("contact-regression-owner@example.test")
    record = Contact.objects.create(owner=person, name="Original")

    with pytest.raises(ValidationError):
        edit_contact(actor=person, contact_id=record.pk, expected_version=0, changes=changes)

    record.refresh_from_db()
    assert record.name == "Original"
    assert record.owner_id == person.pk
    assert record.version == 0


def test_direct_service_rejects_cross_owner_access_even_for_superuser():
    person = actor("contact-isolation-owner@example.test")
    stranger = actor("contact-isolation-admin@example.test", superuser=True)
    record = Contact.objects.create(owner=person, name="Private")

    with pytest.raises(NotFound):
        edit_contact(
            actor=stranger,
            contact_id=record.pk,
            expected_version=0,
            changes={"name": "Stolen"},
        )

    record.refresh_from_db()
    assert record.name == "Private"
    assert record.version == 0


def test_stale_contact_update_keeps_all_fields_unchanged():
    person = actor("contact-stale-owner@example.test")
    record = Contact.objects.create(owner=person, name="Original", phone="123")

    with pytest.raises(StaleContact):
        edit_contact(
            actor=person,
            contact_id=record.pk,
            expected_version=1,
            changes={"name": "Lost", "phone": "999"},
        )

    record.refresh_from_db()
    assert (record.name, record.phone, record.version) == ("Original", "123", 0)
