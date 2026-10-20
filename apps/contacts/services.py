"""Private optimistic contact edits; fields are explicitly allowlisted."""

from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from .models import Contact


class StaleContact(ValidationError):
    status_code = 409
    default_detail = "Contact has changed; refresh and retry."


@transaction.atomic
def edit_contact(*, actor, contact_id, expected_version, changes):
    contact = Contact.objects.select_for_update().filter(pk=contact_id, owner=actor).first()
    if contact is None:
        raise NotFound()
    if contact.version != expected_version:
        raise StaleContact()
    if not changes or not set(changes) <= {"name", "email", "phone", "company", "notes"}:
        raise ValidationError("Invalid or empty changes.")
    for key, value in changes.items():
        setattr(contact, key, value)
    contact.version += 1
    contact.save(update_fields=(*changes.keys(), "version", "updated_at"))
    return contact
