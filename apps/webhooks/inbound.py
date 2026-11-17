"""Verify signature and claim inbound event exactly once at the DB boundary."""

import hashlib
import re

from django.db import IntegrityError, transaction

from apps.webhooks.models import InboundReceipt
from apps.webhooks.security import verify

PROVIDER = re.compile(r"^[a-zA-Z0-9_.-]{1,80}$")
# 0xFF never occurs in UTF-8, so no delivery ID can hash to a signature key.
SIGNATURE_KEY_PREFIX = b"\xffsig:"


def _claim(provider: str, key: str) -> bool:
    """Insert one receipt in a savepoint; False if that key was already claimed."""
    try:
        with transaction.atomic():
            InboundReceipt.objects.create(provider=provider, delivery_hash=key)
    except IntegrityError:
        if InboundReceipt.objects.filter(provider=provider, delivery_hash=key).exists():
            return False
        raise
    return True


def accept(
    *,
    provider: str,
    delivery_id: str,
    body: bytes,
    timestamp: str,
    signature: str,
    secret: str,
    processor,
    now=None,
) -> bool:
    """Run trusted synchronous processor(body) inside receipt transaction.

    False means this provider already processed either this delivery ID or
    these exact signed bytes. The delivery ID is not covered by the HMAC, so
    the verified signature is claimed too: a captured request replayed under
    another delivery ID is not processed again. If processor raises, receipts
    and associated business writes roll back together.
    """
    if not isinstance(provider, str) or not PROVIDER.fullmatch(provider):
        raise ValueError("Invalid webhook provider")
    if not isinstance(delivery_id, str) or not 1 <= len(delivery_id) <= 128:
        raise ValueError("Invalid webhook delivery ID")
    if not callable(processor):
        raise ValueError("Webhook processor must be a trusted callable")
    verify(secret=secret, body=body, timestamp=timestamp, signature=signature, now=now)
    signed_key = hashlib.sha256(SIGNATURE_KEY_PREFIX + signature.encode("ascii")).hexdigest()
    delivery_key = hashlib.sha256(delivery_id.encode("utf-8")).hexdigest()
    with transaction.atomic():
        # Signature first: a replay must return before it can reserve the
        # delivery ID of an event the provider has not sent yet. A signature
        # seen on a duplicate delivery stays claimed so it cannot be replayed.
        if not _claim(provider, signed_key) or not _claim(provider, delivery_key):
            return False
        processor(body)
        return True
