"""Transport-agnostic HMAC signing with bounded body and replay window."""

import hashlib
import hmac
import time

MAX_BODY_BYTES = 64 * 1024
MAX_SKEW_SECONDS = 300


class InvalidWebhookSignature(ValueError):
    pass


def _require_body(body: bytes):
    if not isinstance(body, bytes) or len(body) > MAX_BODY_BYTES:
        raise InvalidWebhookSignature("Invalid webhook body")


def sign(*, secret: str, body: bytes, timestamp: int) -> str:
    if not isinstance(secret, str) or len(secret) < 32:
        raise ValueError("Webhook HMAC secret must contain at least 32 characters")
    _require_body(body)
    if type(timestamp) is not int or timestamp <= 0:
        raise ValueError("Invalid timestamp")
    signed = str(timestamp).encode("ascii") + b"." + body
    return hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def verify(*, secret: str, body: bytes, timestamp: str, signature: str, now=None):
    _require_body(body)
    if not isinstance(timestamp, str) or not timestamp.isascii() or not timestamp.isdecimal():
        raise InvalidWebhookSignature("Invalid webhook timestamp")
    value = int(timestamp)
    current = int(time.time()) if now is None else int(now)
    if abs(current - value) > MAX_SKEW_SECONDS:
        raise InvalidWebhookSignature("Webhook timestamp outside allowed window")
    if not isinstance(signature, str) or len(signature) != 64:
        raise InvalidWebhookSignature("Missing webhook signature")
    expected = sign(secret=secret, body=body, timestamp=value)
    if not hmac.compare_digest(expected, signature):
        raise InvalidWebhookSignature("Invalid webhook signature")
