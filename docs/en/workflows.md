# Portable Workflows (#46)

**Language:** English · [Русский](../workflows.md) · [Docs index](README.md)

`apps/workflows` separates a client-defined **pure Python state machine** from optional Django persistence. It does not register a generic HTTP API, define user roles, create a customer/order model or require a broker.

A client constructs a `WorkflowDefinition` with known states, an initial state, terminal states and `TransitionRule` entries specifying action, permitted transition, optional actor permission and business guard.

The client **owns** its aggregate's `workflow_state` and `workflow_version` (it can use the abstract `WorkflowStateMixin`). Use the service `advance(...)` with a pre-scoped `queryset`, `expected_version`, action, trusted scope, actor, explicit `authorize` callback and `record_history=True` when a durable transition log is required.

## Concurrency and audit

The command runs in `transaction.atomic`, locks the target via `select_for_update`, rechecks access, expected version, transition and guards, then uses a conditional update to avoid lost writes. History uses unique `(scope, aggregate_id, version)`; events have a deterministic ID. Invalid transitions, guards, permissions and stale versions fail explicitly.

The optional audit hook executes **inside the transaction** and must perform only rollbackable database actions. Send external events through an optional Outbox and require consumer idempotency; history does not automatically publish a message. SQLite does not prove real row-lock behavior — validate with PostgreSQL concurrency tests.

## Install

```bash
uv run python scripts/new_project.py ../flow-api --name flow-api --apps workflows
cd ../flow-api
uv run python manage.py makemigrations users workflows
uv run python manage.py migrate
```

Never change client migration histories in-place. [Full API integration example (RU)](../workflows.md).
