"""Signed HTTPS delivery for trusted configured endpoints; retry via Outbox."""

import ipaddress
import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from django.conf import settings

from apps.webhooks.security import MAX_BODY_BYTES, sign


class WebhookDeliveryError(RuntimeError):
    """No URL, secrets or private provider details in the persisted Tasks error."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _config(event_type: str):
    configured = getattr(settings, "WEBHOOK_OUTBOUND_TARGETS", {})
    if not isinstance(configured, dict) or event_type not in configured:
        raise ValueError("Unknown outbound webhook event")
    value = configured[event_type]
    if not isinstance(value, dict):
        raise ValueError("Invalid webhook target config")
    url, secret = value.get("url"), value.get("secret")
    timeout = value.get("timeout", 5)
    if not isinstance(url, str):
        raise ValueError("Invalid webhook endpoint")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("Outbound webhook requires explicit HTTPS endpoint")
    hostname = parsed.hostname.lower()
    if hostname == "localhost" or hostname.endswith(".local"):
        raise ValueError("Outbound endpoint may not address loopback hosts")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError("Outbound endpoint must use a trusted DNS hostname")
    if not isinstance(secret, str) or len(secret) < 32:
        raise ValueError("Outbound webhook requires a strong HMAC secret")
    if type(timeout) not in (int, float) or not 1 <= timeout <= 10:
        raise ValueError("Invalid webhook timeout")
    return url, secret, timeout


def deliver(*, event_type: str, data: dict, event_id: str, transport=None) -> None:
    """Client's outbox handler should call this; failures raise and will retry."""
    if not isinstance(data, dict) or not isinstance(event_id, str) or not event_id:
        raise ValueError("Invalid outbound webhook envelope")
    url, secret, timeout = _config(event_type)
    try:
        body = json.dumps(
            {"id": event_id, "type": event_type, "data": data},
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid outbound JSON") from exc
    if len(body) > MAX_BODY_BYTES:
        raise ValueError("Outbound webhook body too large")
    import time

    timestamp = int(time.time())
    signature = sign(secret=secret, body=body, timestamp=timestamp)
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Timestamp": str(timestamp),
            "X-Webhook-Signature": signature,
            "X-Webhook-Delivery": event_id,
        },
        method="POST",
    )
    client = transport or urllib.request.build_opener(_NoRedirect())
    try:
        with client.open(request, timeout=timeout) as response:
            if not 200 <= response.status < 300:
                raise WebhookDeliveryError("Webhook receiver rejected delivery")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise WebhookDeliveryError("Webhook endpoint did not accept delivery") from exc
