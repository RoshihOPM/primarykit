# PostgreSQL transactional Idempotency

The optional `idempotency` module provides a durable, unique
`(scope, key)` receipt for **database** operations. No route/middleware is
registered. Only PostgreSQL supports its concurrency contract; SQLite tests
validate inputs but cannot validate locking.

```python
from apps.idempotency.services import execute_once

response, replayed = execute_once(
    scope=f"users:{request.user.pk}:orders.create",
    key=validated_idempotency_key,
    request={"items": validated_items},
    operation=lambda: create_order_and_outbox_event(...),
)
```

Build `scope` from **server-authorized** principal, tenant and command. Do not
use caller-controlled actor or organization IDs. Canonical JSON request hashes
are compared, request/response capped at 64 KiB, key capped at 128 characters.
Same input replays the response; a different input with the same key raises
`IdempotencyConflict` (typically return HTTP 409).

PostgreSQL uniqueness and `select_for_update` serialize competing writers
within `transaction.atomic()`. A raised exception rolls back the receipt and
domain DB writes. All client apps own and commit their migration files.

**This does NOT guarantee exactly-once emails, payment captures, or HTTP
calls.** Make the operation database-only; use transactional Outbox and
idempotent external consumers. Receipts have no automatic deletion; client
retention policy must exceed the retry horizon and account for PII rules.
Never silently fall back to Redis or per-process locks.
