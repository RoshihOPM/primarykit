# Inventory v0.1 — transactional warehouse stock

Inventory is an **optional** Django app that depends on Catalog; the generator automatically selects `catalog` when `inventory` is chosen. There is no tenant or organization boundary in v0.1. All Inventory endpoints (read/write) are restricted to **active superusers**, and write services repeat this check even when called outside HTTP.

## Domain schema and invariants

- `Warehouse`: UUID, code, name, active.
- `StockBalance`: unique (warehouse, item), `on_hand >= reserved >= 0` enforced by PostgreSQL CHECK + nonnegative fields, `available = on_hand - reserved`.
- `StockReservation`: amount on one balance, ACTIVE → RELEASED or CONSUMED, irreversible.
- `InventoryOperation`: unique client idempotency key, actor, request fingerprint and result snapshot.
- `StockMovement`: append-only physical/held deltas tied to operation and balance, including two entries for transfers. Normal ORM update/delete is rejected; SQL admin can still modify history.

The journal is the **audit trail of all operations made through services**; balance is the transactionally maintained materialization for fast queries. A damaged balance can be reconstructed from movement deltas. There is no row update API for balance or movement.

## Write operations

`POST /api/v1/inventory/operations/` accepts a strict command envelope with `kind`, `idempotency_key` (minimum 8 characters), and kind-specific fields.

| Kind | Fields | Effect |
| --- | --- | --- |
| receive | warehouse, item, quantity | on_hand +quantity |
| issue | warehouse, item, quantity | on_hand -quantity, only from available |
| transfer | warehouse, destination, item, quantity | on_hand -quantity/+quantity, two ledger rows |
| reserve | warehouse, item, quantity | reserved +quantity, creates reservation |
| release | reservation | reserved -reserved_quantity |
| consume | reservation | reserved -quantity, on_hand -quantity |

All business writes, movement rows, idempotency results and optional Audit event are committed under the **same** `transaction.atomic()`. Operations use `select_for_update` on balances and consistent row lock ordering; concurrent requests must be tested against PostgreSQL. Unique idempotency keys reject mismatched replays and return the original JSON result for matching retries.

`GET /api/v1/inventory/warehouses/`, `GET /balances/`, `GET /reservations/`, `GET /operations/` are administrative only; warehouse create/PATCH also superuser-only. No direct inventory mutations via serializers or generic CRUD.

## Limitations / next steps

- Positive **integer quantities** only. Precision, units of measure, lots/batches, serial numbers, expiration and stock costing need domain-specific follow-ups.
- Reservations have no timeout, TTL or partial fulfillment yet; release/consume operates on the full reservation. Store expiry and cleanup as explicit commands later.
- Default owner of every stock record is the application. A tenant/organization membership model must be introduced before delegating inventory management to different businesses/branches.
- Inactive warehouse/catalog items block new receives/issues/transfers/reserves; existing reservations can still close.
- Ledger is append-only via ORM but database administrators can manipulate it; production compliance requires additional DB permissions, retention and reconciliation.
- Idempotency keys are globally unique within the project; callers should use UUID-like random keys to avoid collisions. Key reuse by a different user is not accepted.
- Use `EXPLAIN (ANALYZE, BUFFERS)` with realistic data before inventing indexes or partitioning. Hot SKUs may contend on a single balance row and require monitoring.
- No background worker needed for current commands. If a queue is added, preserve the same services and idempotency contract.

## Migration policy

In a *new* generated client project run `makemigrations users catalog inventory` and commit generated migrations. On an existing client project **never delete prior migration history**, review new migrations with database architect and deploy using a safe expand/contract strategy.
