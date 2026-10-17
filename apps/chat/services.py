"""Fail-closed owner/tenant authorization, sequence allocation and retention."""

from datetime import timedelta
from uuid import UUID

from django.apps import apps as django_apps
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.users.models import User

from .domain import canonical_pair, normalize_message_body
from .models import Dialogue, Message


def _verify_person(user):
    if not user or not user.is_authenticated or not user.is_active:
        raise NotFound()
    if getattr(settings, "AUTH_REQUIRE_EMAIL_VERIFICATION", True) and not user.email_verified:
        raise NotFound()


def _member_in_org(user, organization_id, *, lock=False):
    if not django_apps.is_installed("apps.organizations"):
        raise NotFound()
    from apps.organizations.models import Membership

    query = Membership.objects.filter(
        user=user,
        organization_id=organization_id,
        organization__is_active=True,
        is_active=True,
    )
    if lock:
        query = query.select_for_update()
    if not query.exists():
        raise NotFound()


def visible_dialogues(user):
    _verify_person(user)
    query = Dialogue.objects.filter(Q(user_low=user) | Q(user_high=user))
    if not django_apps.is_installed("apps.organizations"):
        return query.filter(organization_id__isnull=True)
    from apps.organizations.models import Membership

    allowed_ids = Membership.objects.filter(
        user=user, is_active=True, organization__is_active=True
    ).values_list("organization_id", flat=True)
    return query.filter(Q(organization_id__isnull=True) | Q(organization_id__in=allowed_ids))


def get_dialogue(*, actor, dialogue_id, lock=False):
    query = visible_dialogues(actor)
    if lock:
        query = query.select_for_update()
    dialogue = query.filter(pk=dialogue_id).first()
    if dialogue is None:
        raise NotFound()
    if dialogue.organization_id is not None:
        _member_in_org(actor, dialogue.organization_id, lock=lock)
    return dialogue


def create_dialogue(*, actor, recipient_id, organization_id=None):
    _verify_person(actor)
    try:
        recipient_id = UUID(str(recipient_id))
        if organization_id is not None:
            organization_id = UUID(str(organization_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError("Invalid participant or organization ID.") from exc
    recipient = User.objects.filter(pk=recipient_id, is_active=True).first()
    if recipient is None:
        raise NotFound()
    _verify_person(recipient)
    try:
        low, high = canonical_pair(actor.pk, recipient.pk)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    if organization_id is not None:
        _member_in_org(actor, organization_id)
        _member_in_org(recipient, organization_id)
    scope_key = str(organization_id) if organization_id else "personal"
    with transaction.atomic():
        if organization_id is not None:
            _member_in_org(actor, organization_id, lock=True)
            _member_in_org(recipient, organization_id, lock=True)
        dialogue, _ = Dialogue.objects.get_or_create(
            user_low_id=low,
            user_high_id=high,
            scope_key=scope_key,
            defaults={"organization_id": organization_id},
        )
    return dialogue


def _attachment_for(*, actor, dialogue, attachment_id):
    if not django_apps.is_installed("apps.storage"):
        raise ValidationError({"attachment_id": "Storage module is not installed."})
    from apps.storage.models import StoredFile

    attached = StoredFile.objects.filter(
        pk=attachment_id,
        organization_id=dialogue.organization_id,
        owner=actor,
        deleted_at__isnull=True,
    ).first()
    if attached is None:
        raise NotFound()
    return attached


def send_message(*, actor, dialogue_id, body="", attachment_id=None):
    try:
        normalized = normalize_message_body(body, has_attachment=attachment_id is not None)
    except ValueError as exc:
        raise ValidationError({"body": str(exc)}) from exc
    with transaction.atomic():
        dialogue = get_dialogue(actor=actor, dialogue_id=dialogue_id, lock=True)
        if attachment_id is not None:
            _attachment_for(actor=actor, dialogue=dialogue, attachment_id=attachment_id)
        dialogue.last_sequence += 1
        dialogue.save(update_fields=("last_sequence", "updated_at"))
        retention_days = getattr(settings, "CHAT_RETENTION_DAYS", 30)
        if not isinstance(retention_days, int) or retention_days < 1:
            raise ValueError("CHAT_RETENTION_DAYS must be a positive integer")
        message = Message.objects.create(
            dialogue=dialogue,
            sender=actor,
            sequence=dialogue.last_sequence,
            body=normalized,
            attachment_id=attachment_id,
            expires_at=timezone.now() + timedelta(days=retention_days),
        )
    return message


def visible_messages(*, actor, dialogue_id, after=0, limit=50):
    dialogue = get_dialogue(actor=actor, dialogue_id=dialogue_id)
    messages = list(
        Message.objects.filter(
            dialogue=dialogue, sequence__gt=after, expires_at__gt=timezone.now()
        ).order_by("sequence")[:limit]
    )
    return dialogue, messages


def mark_read(*, actor, dialogue_id, sequence):
    with transaction.atomic():
        dialogue = get_dialogue(actor=actor, dialogue_id=dialogue_id, lock=True)
        if sequence > dialogue.last_sequence:
            raise ValidationError({"sequence": "Sequence exceeds the latest message."})
        column = "low_read_sequence" if actor.pk == dialogue.user_low_id else "high_read_sequence"
        new_value = max(getattr(dialogue, column), sequence)
        if new_value != getattr(dialogue, column):
            setattr(dialogue, column, new_value)
            dialogue.save(update_fields=(column, "updated_at"))
        return new_value


def get_message_attachment(*, actor, dialogue_id, message_id):
    dialogue = get_dialogue(actor=actor, dialogue_id=dialogue_id)
    message = Message.objects.filter(
        pk=message_id,
        dialogue=dialogue,
        attachment_id__isnull=False,
        expires_at__gt=timezone.now(),
    ).first()
    if message is None:
        raise NotFound()
    if not django_apps.is_installed("apps.storage"):
        raise NotFound()
    from apps.storage.models import StoredFile

    attached = StoredFile.objects.filter(
        pk=message.attachment_id,
        organization_id=dialogue.organization_id,
        deleted_at__isnull=True,
    ).first()
    if attached is None:
        raise Http404()
    # The creator is required to own this file at the moment it is attached.
    return attached
