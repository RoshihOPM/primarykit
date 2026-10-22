"""Boundary cases for signed webhooks and outbound SSRF prevention."""

import pytest
from django.test import override_settings

from apps.webhooks.inbound import accept
from apps.webhooks.models import InboundReceipt
from apps.webhooks.outbound import deliver
from apps.webhooks.security import MAX_BODY_BYTES, InvalidWebhookSignature, sign

SECRET = "w" * 40


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/hooks",
        "https://192.168.1.10/hooks",
        "https://[::1]/hooks",
        "https://localhost/hooks",
        "https://service.local/hooks",
        "https://user:pass@events.example.com/hooks",
        "https://events.example.com/hooks#secret",
    ],
)
def test_outbound_rejects_local_hosts_ip_literals_and_credential_urls(url):
    with override_settings(
        WEBHOOK_OUTBOUND_TARGETS={"lead.created": {"url": url, "secret": SECRET}}
    ):
        with pytest.raises(ValueError):
            deliver(event_type="lead.created", data={}, event_id="event-one")


def test_oversized_outbound_body_never_reaches_transport():
    class MustNotCall:
        def open(self, request, timeout):
            raise AssertionError("oversized payload reached the transport")

    with override_settings(
        WEBHOOK_OUTBOUND_TARGETS={
            "lead.created": {"url": "https://events.example.com/hooks", "secret": SECRET}
        }
    ):
        with pytest.raises(ValueError, match="too large"):
            deliver(
                event_type="lead.created",
                data={"payload": "x" * (MAX_BODY_BYTES + 1)},
                event_id="oversized",
                transport=MustNotCall(),
            )


@pytest.mark.django_db
def test_invalid_inbound_signature_does_not_claim_delivery_id():
    body = b'{"id":"source-event"}'
    called = []
    with pytest.raises(InvalidWebhookSignature):
        accept(
            provider="shipping",
            delivery_id="event-one",
            body=body,
            timestamp="1000",
            signature="0" * 64,
            secret=SECRET,
            processor=called.append,
            now=1000,
        )
    assert not called
    assert not InboundReceipt.objects.exists()


@pytest.mark.django_db
def test_same_delivery_id_in_different_providers_is_independent():
    body = b'{"id":"source-event"}'
    signature = sign(secret=SECRET, body=body, timestamp=1000)
    seen = []
    for provider in ("shipping", "billing"):
        assert accept(
            provider=provider,
            delivery_id="shared-id",
            body=body,
            timestamp="1000",
            signature=signature,
            secret=SECRET,
            processor=seen.append,
            now=1000,
        )
    assert seen == [body, body]
    assert InboundReceipt.objects.count() == 2
