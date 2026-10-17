"""HTTP, scope, object-access, retention and PostgreSQL concurrency tests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.db import connection, connections
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.chat.domain import canonical_pair, normalize_message_body
from apps.chat.models import Dialogue, Message
from apps.chat.services import create_dialogue, send_message
from apps.users.models import User

pytestmark = pytest.mark.django_db


def account(email, *, staff=False, superuser=False):
    user = User.objects.create_user(
        email=email,
        password="Long-test-password-916",
        email_verified=True,
        is_staff=staff,
        is_superuser=superuser,
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return user, client


def test_pure_domain_rules():
    assert normalize_message_body("  hello  ") == "hello"
    assert normalize_message_body("", has_attachment=True) == ""
    for bad in (" ", "x" * 4001, None):
        with pytest.raises(ValueError):
            normalize_message_body(bad)
    low, high = canonical_pair(uuid4(), uuid4())
    assert low < high
    with pytest.raises(ValueError):
        canonical_pair(low, low)


def test_private_dialogue_idor_including_staff_and_superuser():
    alice, a = account("private-a@example.test")
    bob, b = account("private-b@example.test")
    _, outsider = account("private-x@example.test")
    _, admin = account("private-admin@example.test", staff=True, superuser=True)
    created = a.post(reverse("chat-list"), {"recipient_id": str(bob.pk)}, format="json")
    assert created.status_code == 201, created.data
    chat_id = created.data["id"]
    assert a.post(reverse("chat-list"), {"recipient_id": str(bob.pk)}).data["id"] == chat_id
    assert b.post(reverse("chat-list"), {"recipient_id": str(alice.pk)}).data["id"] == chat_id
    assert a.get(reverse("chat-list")).data["count"] == 1
    assert b.get(reverse("chat-detail", kwargs={"pk": chat_id})).status_code == 200
    for stranger in (outsider, admin):
        assert stranger.get(reverse("chat-list")).data["count"] == 0
        assert stranger.get(reverse("chat-detail", kwargs={"pk": chat_id})).status_code == 404
        assert (
            stranger.post(
                reverse("chat-messages", kwargs={"pk": chat_id}), {"body": "hijack"}
            ).status_code
            == 404
        )
        assert (
            stranger.post(reverse("chat-read", kwargs={"pk": chat_id}), {"sequence": 0}).status_code
            == 404
        )
    assert APIClient().get(reverse("chat-list")).status_code in (401, 403)


def test_message_sequence_cursor_read_receipts_and_mass_assignment():
    alice, a = account("seq-a@example.test")
    bob, b = account("seq-b@example.test")
    chat_id = a.post(reverse("chat-list"), {"recipient_id": str(bob.pk)}).data["id"]
    url = reverse("chat-messages", kwargs={"pk": chat_id})
    assert a.post(url, {"body": "   "}).status_code == 400
    first = a.post(url, {"body": " one ", "sender": str(bob.pk), "sequence": 1000})
    second = b.post(url, {"body": "two"})
    assert first.status_code == second.status_code == 201
    assert first.data["body"] == "one"
    assert first.data["sender"] == str(alice.pk)
    assert first.data["sequence"] == 1
    assert second.data["sequence"] == 2
    assert len(a.get(url + "?after=1").data["results"]) == 1
    assert a.get(url + "?after=1").data["next_after"] == 2
    assert a.get(url + "?after=999").data["results"] == []
    for suffix in ("?limit=51", "?after=-1", "?after=not-an-int"):
        assert a.get(url + suffix).status_code == 400
    read = reverse("chat-read", kwargs={"pk": chat_id})
    assert b.post(read, {"sequence": 2}).data["read_sequence"] == 2
    assert b.post(read, {"sequence": 1}).data["read_sequence"] == 2
    assert a.post(read, {"sequence": 3}).status_code == 400
    dialogue = Dialogue.objects.get(pk=chat_id)
    assert dialogue.last_sequence == 2


def test_invalid_recipient_and_unverified_or_disabled_identity():
    person, api = account("invalid-a@example.test")
    disabled, _ = account("invalid-b@example.test")
    unverified, _ = account("invalid-c@example.test")
    disabled.is_active = False
    disabled.save(update_fields=("is_active",))
    unverified.email_verified = False
    unverified.save(update_fields=("email_verified",))
    for target in (person.pk, disabled.pk, unverified.pk, uuid4()):
        assert api.post(reverse("chat-list"), {"recipient_id": str(target)}).status_code in (
            400,
            404,
        )
    assert not Dialogue.objects.exists()


def test_tenant_boundaries_and_membership_revocation():
    from apps.organizations.models import Membership, Organization

    alice, a = account("tenant-chat-a@example.test")
    bob, b = account("tenant-chat-b@example.test")
    _, stranger = account("tenant-chat-x@example.test")
    org = Organization.objects.create(slug="tenant-chat", name="Tenant Chat")
    other = Organization.objects.create(slug="tenant-chat-foreign", name="Other")
    for user in (alice, bob):
        Membership.objects.create(organization=org, user=user)
    Membership.objects.create(organization=other, user=alice)
    url = reverse("chat-list")
    assert (
        a.post(url, {"recipient_id": str(bob.pk), "organization_id": str(other.pk)}).status_code
        == 404
    )
    created = a.post(url, {"recipient_id": str(bob.pk), "organization_id": str(org.pk)})
    assert created.status_code == 201, created.data
    chat_id = created.data["id"]
    assert stranger.get(reverse("chat-detail", kwargs={"pk": chat_id})).status_code == 404
    Membership.objects.filter(organization=org, user=bob).update(is_active=False)
    assert b.get(reverse("chat-list")).data["count"] == 0
    assert b.get(reverse("chat-detail", kwargs={"pk": chat_id})).status_code == 404
    assert (
        b.post(reverse("chat-messages", kwargs={"pk": chat_id}), {"body": "x"}).status_code == 404
    )
    assert a.get(reverse("chat-detail", kwargs={"pk": chat_id})).status_code == 200


def test_attachment_owner_scope_and_revocation():
    from apps.storage.models import StoredFile

    alice, a = account("att-a@example.test")
    bob, b = account("att-b@example.test")
    chat_id = a.post(reverse("chat-list"), {"recipient_id": str(bob.pk)}).data["id"]
    url = reverse("chat-messages", kwargs={"pk": chat_id})
    foreign = StoredFile.objects.create(
        owner=bob,
        object_key="private/foreign-chat",
        original_name="x.pdf",
        size=8,
        content_type="application/pdf",
        sha256="a" * 64,
    )
    assert a.post(url, {"attachment_id": str(foreign.pk)}).status_code == 404
    own = StoredFile.objects.create(
        owner=alice,
        object_key="private/owned-chat",
        original_name="x.pdf",
        size=8,
        content_type="application/pdf",
        sha256="b" * 64,
    )
    posted = a.post(url, {"attachment_id": str(own.pk)})
    assert posted.status_code == 201, posted.data
    assert posted.data["body"] == ""
    download = reverse("chat-attachment", kwargs={"pk": chat_id, "message_id": posted.data["id"]})
    assert b.get(download).status_code == 404  # blob not uploaded
    own.deleted_at = timezone.now()
    own.save(update_fields=("deleted_at",))
    assert b.get(download).status_code == 404


@override_settings(CHAT_RETENTION_DAYS=1)
def test_retention_and_explicit_purge_keep_cursor_monotonic():
    alice, a = account("ttl-a@example.test")
    bob, _ = account("ttl-b@example.test")
    chat = create_dialogue(actor=alice, recipient_id=bob.pk)
    msg = send_message(actor=alice, dialogue_id=chat.pk, body="private")
    Message.objects.filter(pk=msg.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    assert a.get(reverse("chat-messages", kwargs={"pk": chat.pk})).data["results"] == []
    call_command("purge_expired_chat")
    assert not Message.objects.filter(pk=msg.pk).exists()
    assert send_message(actor=alice, dialogue_id=chat.pk, body="later").sequence == 2


@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_senders_have_monotonic_sequences():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row locks required")
    alice, _ = account("pg-chat-a@example.test")
    bob, _ = account("pg-chat-b@example.test")
    chat = create_dialogue(actor=alice, recipient_id=bob.pk)

    def publish(index):
        try:
            return send_message(actor=alice, dialogue_id=chat.pk, body=str(index)).sequence
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=4) as pool:
        sequences = sorted(pool.map(publish, range(12)))
    assert sequences == list(range(1, 13))
