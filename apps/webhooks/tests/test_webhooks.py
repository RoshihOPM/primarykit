"""Inbound replay protection and outbound transport safety."""

import json

import pytest
from django.test import override_settings

from apps.webhooks.inbound import accept
from apps.webhooks.models import InboundReceipt
from apps.webhooks.outbound import WebhookDeliveryError, deliver
from apps.webhooks.security import InvalidWebhookSignature, sign, verify

SECRET = "x" * 40
BODY = b'{"id":"source-event"}'


def test_hmac_verification_and_timestamp_rejection():
    sig = sign(secret=SECRET, body=BODY, timestamp=1000)
    verify(secret=SECRET, body=BODY, timestamp="1000", signature=sig, now=1001)
    for changed in ("wrong", "999999"):
        with pytest.raises(InvalidWebhookSignature):
            verify(secret=SECRET, body=BODY, timestamp=changed, signature=sig, now=1001)
    with pytest.raises(InvalidWebhookSignature):
        verify(secret=SECRET, body=BODY + b"x", timestamp="1000", signature=sig, now=1001)
    with pytest.raises(InvalidWebhookSignature):
        verify(secret=SECRET, body=BODY, timestamp="1000", signature=sig, now=2000)


@pytest.mark.django_db
def test_inbound_receipt_idempotency_and_rollback():
    signature = sign(secret=SECRET, body=BODY, timestamp=1000)
    seen = []
    kwargs = dict(
        provider="shipping",
        delivery_id="evt-123",
        body=BODY,
        timestamp="1000",
        signature=signature,
        secret=SECRET,
        now=1000,
    )
    assert accept(**kwargs, processor=seen.append)
    assert not accept(**kwargs, processor=seen.append)
    assert seen == [BODY]
    assert InboundReceipt.objects.count() == 1
    assert "evt-123" not in InboundReceipt.objects.first().delivery_hash

    def fail(body):
        raise RuntimeError("business failed")

    with pytest.raises(RuntimeError, match="business failed"):
        accept(**{**kwargs, "delivery_id": "new-event"}, processor=fail)
    assert InboundReceipt.objects.count() == 1


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeTransport:
    def __init__(self):
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        return FakeResponse()


@override_settings(
    WEBHOOK_OUTBOUND_TARGETS={
        "lead.created": {"url": "https://events.example.com/hooks", "secret": SECRET},
    }
)
def test_outbound_signs_and_sends_json_to_allowlisted_https_target():
    fake = FakeTransport()
    deliver(
        event_type="lead.created", data={"lead_id": "42"}, event_id="event-uuid", transport=fake
    )
    request, timeout = fake.calls[0]
    assert request.full_url == "https://events.example.com/hooks"
    assert timeout == 5
    payload = json.loads(request.data)
    assert payload == {
        "id": "event-uuid",
        "type": "lead.created",
        "data": {"lead_id": "42"},
    }
    verify(
        secret=SECRET,
        body=request.data,
        timestamp=request.get_header("X-webhook-timestamp"),
        signature=request.get_header("X-webhook-signature"),
    )


@override_settings(
    WEBHOOK_OUTBOUND_TARGETS={
        "lead.created": {"url": "http://127.0.0.1/private", "secret": SECRET},
    }
)
def test_outbound_rejects_insecure_target():
    with pytest.raises(ValueError, match="HTTPS"):
        deliver(event_type="lead.created", data={}, event_id="id", transport=FakeTransport())


@override_settings(
    WEBHOOK_OUTBOUND_TARGETS={
        "lead.created": {"url": "https://events.example.com/hooks", "secret": SECRET},
    }
)
def test_outbound_network_failure_raises_for_outbox_retry():
    class UnavailableTransport:
        def open(self, _request, timeout):
            raise TimeoutError("external transport secret")

    with pytest.raises(WebhookDeliveryError, match="did not accept"):
        deliver(
            event_type="lead.created",
            data={},
            event_id="stable-event-id",
            transport=UnavailableTransport(),
        )
