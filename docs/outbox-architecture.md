# Outbox — durable events on top of Tasks

`--apps outbox` automatically selects `tasks`; there is no second event table, RabbitMQ, Redis, or mandatory Celery. Both modules are copied into the new backend and run independently of PrimaryKit. Each client owns its migrations and registered event handlers.

## Delivery contract

A business service invokes `emit()` *inside the same transaction.atomic()* that changes business records. The outbox event is inserted as `apps.tasks.BackgroundJob` in the same PostgreSQL transaction. No task is published before commit. A separate `run_background_jobs` worker polls and invokes a **trusted** application handler, which may publish to Celery/RabbitMQ, send an HTTP webhook, or perform an internal side effect.

```python
from django.db import transaction
from apps.outbox.services import emit

with transaction.atomic():
    lead.status = "accepted"
    lead.save(update_fields=["status"])
    emit(
        event_type="lead.accepted",
        body={"lead_id": str(lead.pk)},  # identifiers only; avoid PII
        namespace="org:" + str(organization.pk),
        idempotency_key="accept:" + str(lead.pk),
    )
```

Client settings:

```python
OUTBOX_EVENT_HANDLERS = {
    "lead.accepted": "apps.leads.outbox_handlers.publish_lead_accepted",
}
```

Example business handler in **the generated backend**:

```python
def publish_lead_accepted(body, *, event_id):
    # Re-check authoritative state from PostgreSQL and pass event_id as a
    # downstream idempotency/deduplication token.
    lead_id = body["lead_id"]
    # Trusted task: celery_task.apply_async(kwargs={"lead_id": lead_id, "event_id": event_id})
```

Dispatcher handler `outbox.dispatch` is registered in `BACKGROUND_JOB_HANDLERS` only when Outbox is installed. The user cannot submit arbitrary Python import paths. An absent handler fails and remains retryable. Handlers must not trust inbound body fields for authorization.

### Delivery guarantees

- Outbox record is committed or rolled back together with business data.
- PostgreSQL Tasks uses `SELECT FOR UPDATE SKIP LOCKED`, leases, retry/backoff, and terminal failed state.
- `event_id` remains stable across retries, and repeated `(namespace, event_type, idempotency_key)` returns the same persisted job if content matches.
- **At-least-once**, not exactly-once. A crash after an external publish but before acknowledging the DB row can deliver it again. Every downstream consumer must deduplicate by `event_id` using its own durable store, ideally an inbox uniqueness constraint.
- HTTP/webhook/Celery delivery errors should raise exceptions to trigger job retry. Configure max retry time, delivery alerts and redrive policy.
- Do not store secrets, auth tokens, or unnecessary personal data in the event envelope. DB retention must be decided in each product, particularly where personal data must be erased.

Start worker in a separate process: `python manage.py run_background_jobs`. Outbox uses the Tasks module's `BACKGROUND_JOB_HANDLERS` and job table, so migration command includes `tasks` only. Do **not** run `makemigrations` automatically in production.

See [Tasks](tasks-architecture.md) and [Celery](celery-rabbitmq.md).
