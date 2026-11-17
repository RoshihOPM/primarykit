# Signed Webhooks — inbound deduplication + outgoing delivery

`--apps webhooks` copies independent `apps/webhooks`, and transitively `outbox` and `tasks`. No mandatory Celery, RabbitMQ, Redis, upstream PrimaryKit service or shared migrations.

## Inbound

The module **does not expose public routes**. Client Django views must explicitly define a provider-specific endpoint, enforce HTTP POST and body-size limits, retrieve a secret from safe settings, then invoke:

```python
from apps.webhooks.inbound import accept

processed = accept(
    provider="shipping",
    delivery_id=request.headers["X-Webhook-Delivery"],
    timestamp=request.headers["X-Webhook-Timestamp"],
    signature=request.headers["X-Webhook-Signature"],
    secret=settings.SHIPPING_HMAC_SECRET,
    body=request.body,
    processor=handle_verified_shipping_event,
)
```

`handle_verified_shipping_event(body: bytes)` belongs to this generated client and must parse/validate provider JSON. The module checks HMAC-SHA256 of `timestamp + b"." + body` in constant time, rejects signatures outside a 300-second clock window, caps payloads at 64 KiB, and atomically claims two `InboundReceipt` rows in PostgreSQL before processing: one for the verified signature (`sha256(0xFF + "sig:" + signature)`) and one for `sha256(delivery_id)`. Duplicate deliveries and replays return `False`, while processor exceptions roll back both receipts so retries are possible. Unique DB constraint handles concurrency. Only secret owners can produce fresh signed payloads; never use a user-supplied provider name to choose a Python handler path. Integrations that use a different provider signature scheme should provide a separate validated adapter rather than bypass signature checks.

**The delivery ID is not authenticated.** The HMAC covers only `timestamp + "." + body`; `X-Webhook-Delivery` is an unsigned header that anyone who captured a request can change. `accept()` therefore never relies on it alone:

- identical signed bytes (same provider, timestamp and body) are processed **at most once**, whatever delivery ID accompanies them, so a captured request replayed inside the 300-second window under a new ID returns `False` and cannot reserve the ID of a future event;
- the delivery ID still deduplicates provider retries that are re-signed with a fresh timestamp. Such a retry returns `False` and its signature is remembered as well;
- two legitimate events must differ in signed bytes. A provider that sends byte-identical bodies with the same timestamp second under different delivery IDs gets only the first one processed; put a unique event ID in the signed body (PrimaryKit's own outbound payload does);
- treat the delivery ID as an opaque dedup key only. Never use it for authorization, routing or as a trusted business identifier; take identifiers from the verified body.

Receipts are scoped per `provider`: use a distinct secret for each provider name, otherwise a request signed for one provider is valid for another. Each processed delivery now stores two receipt rows (no schema change); size retention accordingly.

**Important:** do not send irreversible external side effects inside the inbound processor's DB transaction. Instead record domain state and `outbox.emit()` in the same transaction; Outbox asynchronously delivers at-least-once. Webhook endpoint authorization is separate from user JWT authentication and must be explicitly configured.

## Outbound

Configure static trusted destinations in a **client-owned settings module**:

```python
WEBHOOK_OUTBOUND_TARGETS = {
    "lead.created": {
        "url": env("LEAD_WEBHOOK_URL"),  # HTTPS, verified destination
        "secret": env("LEAD_WEBHOOK_SECRET"),  # >=32 characters
        "timeout": 5,
    }
}
OUTBOX_EVENT_HANDLERS = {
    "lead.created": "apps.leads.events.publish_lead_created",
}
```

Client adapter:

```python
from apps.webhooks.outbound import deliver


def publish_lead_created(body, *, event_id):
    deliver(event_type="lead.created", data=body, event_id=event_id)
```

When the business service calls `outbox.emit(event_type="lead.created", ...)` inside `transaction.atomic()`, the durable PostgreSQL worker sends a signed `application/json` POST with delivery ID and timestamp. Non-2xx responses, transport failures and timeouts raise an error; the Tasks worker performs bounded retry/backoff and records `succeeded`/`failed`, attempt count and sanitized error type. Do not interpret HTTP 2xx as end-user fulfillment; it only confirms the receiver accepted the POST.

Only HTTPS trusted destinations from **settings**, no client-supplied URLs. Redirects are disabled to prevent an endpoint bouncing to a private URL. Configure TLS/DNS egress controls and avoid broad outbound network privileges. Delivery is **at-least-once**, so receivers must persist and deduplicate `X-Webhook-Delivery`; stable HMAC signatures alone are not replay-safe without receipt tracking.

### Retention, monitoring, production

InboundReceipt is a client-owned migration. Set a retention policy appropriate to your providers and replay threat model; deleting old receipt rows means an old delivery ID could be reused if an authorized provider signs a fresh timestamp. Never delete receipts younger than the 300-second signature window (keep a generous margin): both the delivery-ID row and the signature row are needed to reject replays of still-valid signed requests. Do not store bodies, secrets or auth headers in the DB. Track `failed` Outbox/Tasks rows, queue age, delivery latency and receiver 4xx/5xx. Do not autostart worker processes in AppConfig or run migrations implicitly in production.
