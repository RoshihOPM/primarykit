# Inventory: company and branch scoped stock

Required: `Organizations` + `Catalog`. PrimaryKit's project generator
selects both automatically for `--apps inventory`.

- `Warehouse` belongs to one organization and one branch of that organization.
  Codes are unique within each organization.
- `StockBalance` belongs to one organization, warehouse and catalog item;
  its parent warehouse and item must have the same organization. Unique
  `(organization, warehouse, item)`, `on_hand >= reserved >= 0`.
- `StockReservation` belongs to a balance and inherits its tenant.
- `InventoryOperation` belongs to an organization and has a per-company
  unique idempotency key, request fingerprint, actor and result.
- `StockMovement` records append-only deltas of each operation/balance.

## API

All endpoints use `/api/v1/organizations/{org_id}/inventory/`.
`warehouses/`, `balances/`, `reservations/` and `operations/` are
nested here; there are no global inventory endpoints.

Membership rules:

| Role | Warehouse/balance | Reservations | Stock commands | Operation history |
| --- | --- | --- | --- | --- |
| owner/admin | All within company | All | Yes | All |
| manager | Assigned active branches | Assigned branches | Yes, assigned branches only | No |
| member | Assigned active branches (read) | No | No | No |
| non-member | 404 | 404 | 404 | 404 |

`POST /operations/` accepts kinds receive, issue, transfer, reserve, release,
consume. All branch/item/reservation references are constrained to the selected
organization before validation. Inside the transaction, the command service
**locks the Organization row**, re-checks current membership and branch grants,
then writes balance, movement, reservation, operation and optional Audit event
atomically. Transfers require permission for both warehouses and the same
company; cross-company transfers are rejected. Reserved units cannot be issued
twice. Closing an existing reservation remains possible if its warehouse is
deactivated, but requires its company membership and appropriate branch grant.

Idempotency key uniqueness is `(organization,key)`; retry of the same request
by the original permitted actor returns the original result. Replay after
membership/branch access is revoked is denied.

## Important limits

Quantities are positive integers; lots, expiry dates, cost valuation, units
of measure, partial reservation fulfillment, and third-party warehouse
integrations belong to domain-specific modules. Ordinary ORM APIs protect
movement immutability, but privileged SQL can tamper with rows. Composite
cross-tenant FK checks depend on service/model validation, not database RLS;
use restricted DB permissions and consider PostgreSQL RLS/triggers if custom
code can write arbitrary tables.

## Upgrading clients with real stock

This is a **breaking schema and route change**. Existing global warehouses
and stock ledgers cannot be placed into arbitrary companies. Plan:
1. Pause writes or use a controlled dual-write/expand migration.
2. Identify and verify organization and branch for each Warehouse.
3. Map each Category/Item and ensure associated balances, reservations and
   operations all resolve to the **same** organization.
4. Backfill new nullable tenant and branch FKs and verify no unmapped rows,
   orphaned references or conflicting per-tenant codes.
5. Set FKs NOT NULL, validate checks/constraints, deploy scoped API routes
   and resume writes.
6. Reconcile all movement deltas against materialized balances and export a
   verified backup before and after deployment.

Never reset, delete or rewrite client migration history. New generated
projects run `makemigrations users organizations catalog inventory`.
