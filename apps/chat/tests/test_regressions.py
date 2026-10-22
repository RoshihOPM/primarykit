"""Transaction guarantees for private message sequences and read receipts."""

import pytest
from django.test import override_settings
from rest_framework.exceptions import NotFound

from apps.chat.models import Dialogue, Message
from apps.chat.services import create_dialogue, mark_read, send_message
from apps.users.models import User

pytestmark = pytest.mark.django_db


def participant(email):
    return User.objects.create_user(
        email=email,
        password="long-chat-regression-password",
        email_verified=True,
    )


def test_invalid_retention_setting_rolls_back_sequence_update():
    alice = participant("chat-rollback-alice@example.test")
    bob = participant("chat-rollback-bob@example.test")
    conversation = create_dialogue(actor=alice, recipient_id=bob.pk)

    with override_settings(CHAT_RETENTION_DAYS=0):
        with pytest.raises(ValueError, match="CHAT_RETENTION_DAYS"):
            send_message(actor=alice, dialogue_id=conversation.pk, body="uncommitted")

    conversation.refresh_from_db()
    assert conversation.last_sequence == 0
    assert not Message.objects.filter(dialogue=conversation).exists()

    delivered = send_message(actor=alice, dialogue_id=conversation.pk, body="retry")
    assert delivered.sequence == 1
    assert Dialogue.objects.get(pk=conversation.pk).last_sequence == 1


def test_direct_service_does_not_allow_unrelated_user_to_mark_messages_read():
    alice = participant("chat-read-alice@example.test")
    bob = participant("chat-read-bob@example.test")
    outsider = participant("chat-read-outsider@example.test")
    conversation = create_dialogue(actor=alice, recipient_id=bob.pk)
    send_message(actor=alice, dialogue_id=conversation.pk, body="private")

    with pytest.raises(NotFound):
        mark_read(actor=outsider, dialogue_id=conversation.pk, sequence=1)

    conversation.refresh_from_db()
    assert conversation.low_read_sequence == 0
    assert conversation.high_read_sequence == 0
