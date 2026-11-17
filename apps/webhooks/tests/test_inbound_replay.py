"""Signed bytes are processed once even when the unsigned delivery ID changes."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections, connection, connections

from apps.webhooks.inbound import accept
from apps.webhooks.models import InboundReceipt
from apps.webhooks.security import sign

SECRET = "r" * 40
BODY = b'{"id":"source-event","amount":100}'
OTHER = b'{"id":"other-event"}'


def _signed(body=BODY, timestamp=1000, **overrides):
    return {
        "provider": "shipping",
        "delivery_id": "evt-1",
        "body": body,
        "timestamp": str(timestamp),
        "signature": sign(secret=SECRET, body=body, timestamp=timestamp),
        "secret": SECRET,
        "now": 1000,
        **overrides,
    }


@pytest.mark.django_db
def test_captured_request_replayed_with_new_delivery_id_is_not_processed_again():
    seen = []
    assert accept(**_signed(), processor=seen.append)
    for forged in ("evt-2", "attacker-chosen", "x" * 128):
        assert not accept(**_signed(delivery_id=forged), processor=seen.append)
    assert seen == [BODY]


@pytest.mark.django_db
def test_replay_cannot_reserve_delivery_ids_of_future_legitimate_events():
    seen = []
    assert accept(**_signed(), processor=seen.append)
    assert not accept(**_signed(delivery_id="evt-2"), processor=seen.append)
    assert accept(**_signed(body=OTHER, delivery_id="evt-2"), processor=seen.append)
    assert seen == [BODY, OTHER]


@pytest.mark.django_db
def test_distinct_signed_deliveries_are_each_processed():
    seen = []
    assert accept(**_signed(), processor=seen.append)
    assert accept(**_signed(body=OTHER, delivery_id="evt-2"), processor=seen.append)
    # Same body signed again at a later second is a new signed message.
    assert accept(**_signed(timestamp=1001, delivery_id="evt-3"), processor=seen.append)
    assert seen == [BODY, OTHER, BODY]


@pytest.mark.django_db
def test_provider_retry_with_fresh_signature_stays_deduplicated_and_unreplayable():
    seen = []
    assert accept(**_signed(), processor=seen.append)
    assert not accept(**_signed(timestamp=1002), processor=seen.append)
    # The retry's signature is remembered although its delivery was a duplicate.
    assert not accept(**_signed(timestamp=1002, delivery_id="evt-9"), processor=seen.append)
    assert seen == [BODY]


@pytest.mark.django_db
def test_failed_processing_releases_signature_and_delivery_claims():
    def fail(_body):
        raise RuntimeError("business failed")

    with pytest.raises(RuntimeError, match="business failed"):
        accept(**_signed(), processor=fail)
    assert not InboundReceipt.objects.exists()
    seen = []
    assert accept(**_signed(), processor=seen.append)
    assert seen == [BODY]


@pytest.mark.django_db
def test_delivery_id_cannot_collide_with_signature_receipt_key():
    """A delivery ID shaped like the signature key must not block or alias anything."""
    seen = []
    signature = _signed()["signature"]
    assert accept(**_signed(delivery_id=f"sig:{signature}"), processor=seen.append)
    upcoming = _signed(body=OTHER)["signature"]
    assert not accept(**_signed(delivery_id=f"sig:{upcoming}"), processor=seen.append)
    assert accept(**_signed(body=OTHER, delivery_id="evt-2"), processor=seen.append)
    assert seen == [BODY, OTHER]
    assert all(len(row.delivery_hash) == 64 for row in InboundReceipt.objects.all())


@pytest.mark.django_db(transaction=True)
def test_concurrent_replays_with_distinct_delivery_ids_process_once():
    if connection.vendor != "postgresql":
        pytest.skip("Real PostgreSQL unique-constraint blocking is required")

    barrier = Barrier(4)
    seen = []

    def worker(number):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            return accept(**_signed(delivery_id=f"race-{number}"), processor=seen.append)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(worker, range(4)))

    assert sorted(results) == [False, False, False, True]
    assert seen == [BODY]
