"""Verify signature and claim inbound event exactly once at the DB boundary."""

import hashlib
import re

from django.db import IntegrityError, transaction

from apps.webhooks.models import InboundReceipt
from apps.webhooks.security import verify

PROVIDER = re.compile(r"^[a-zA-Z0-9_.-]{1,80}$")


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

    False means this provider/delivery ID was already processed. If processor
    raises, receipt and associated business writes roll back together.
    """
    if not isinstance(provider, str) or not PROVIDER.fullmatch(provider):
        raise ValueError("Invalid webhook provider")
    if not isinstance(delivery_id, str) or not 1 <= len(delivery_id) <= 128:
        raise ValueError("Invalid webhook delivery ID")
    if not callable(processor):
        raise ValueError("Webhook processor must be a trusted callable")
    verify(secret=secret, body=body, timestamp=timestamp, signature=signature, now=now)
    digest = hashlib.sha256(delivery_id.encode("utf-8")).hexdigest()
    with transaction.atomic():
        try:
            with transaction.atomic():
                InboundReceipt.objects.create(provider=provider, delivery_hash=digest)
        except IntegrityError:
            if InboundReceipt.objects.filter(provider=provider, delivery_hash=digest).exists():
                return False
            raise
        processor(body)
        return True
