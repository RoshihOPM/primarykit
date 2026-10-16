# ADR 0005 — Standalone Catalog and Inventory with pinned schemas

Status: Accepted for PrimaryKit source catalog (2026-10-16).

## Goal

Copy `apps/catalog/` or `apps/inventory/` into an existing generated PrimaryKit Django
project and run it **without** installing Organizations or the other module.

The previous implementations had hard foreign keys to other bounded contexts:
Catalog -> Organization, Inventory -> Organization + Branch + CatalogItem.
Removing only imports would silently break permissions and database migrations.

## Decision

Both apps have an explicit, **per-project schema mode** in settings, pinned
before the first migration:

- `CATALOG_MODE="standalone"`: Category, AttributeDefinition and CatalogItem
  are owner-scoped. The owner is assigned server-side; no global superuser
  override. Routes start at `/api/v1/catalog/`.
- `CATALOG_MODE="tenant"`: previous company-scoped models and
  `/api/v1/organizations/{org_id}/catalog/` API are preserved.
- `INVENTORY_MODE="standalone"`: Inventory **owns** InventoryItem (SKU), Warehouse,
  StockBalance, StockReservation, InventoryOperation and StockMovement.
  There are no Catalog or Organizations foreign keys. Owner identity is
  checked for every incoming FK and again by application services.
  Stock changes remain transactional, idempotent, immutable-ledger-backed.
  Routes start at `/api/v1/inventory/`, including `/items/`.
- `INVENTORY_MODE="tenant"`: previous company and branch-scoped models,
  CatalogItem relationships and API remain intact.

Manifest dependencies are now optional; the generated project resolves **no**
extra modules merely because Catalog or Inventory was selected. The generator
pins tenant mode when the needed integration modules are selected on creation,
otherwise standalone. Apps use stable facade imports (`models.py`,
`views.py`, `serializers.py`, `services.py`) and implementation adapters
`tenant_*.py` / `standalone_*.py`.

## Schema safety and integration

A project **must not change either MODE setting** after initial migrations,
and must not infer or flip mode when another app folder appears. Switching
a populated standalone Inventory to tenant Inventory is **not** a settings
change: it changes FKs, stock identities, ledgers and operation idempotency
partitions. A future migration must reconcile item mappings, owner to
organization membership, warehouse to branch ownership, and immutable
movement histories before a mode change is permitted.

Tenant APIs are still protected against cross-company, cross-branch and
revoked-role access. Standalone APIs are protected against cross-owner,
superuser and direct service-layer IDOR. No implicit synchronization is
implemented between `InventoryItem` and `CatalogItem`. In standalone
mode, inventory has its own explicit SKU namespace.

`tenant` mode can be selected only with installed required modules. A
mismatched deployment must fail closed at Django URL configuration.

## Trade-offs

This is **two explicit schema adapters in one copyable folder**, not one
universal schema. It is intentionally an all-or-nothing choice made before
migrations. Duplicating a small ORM/API adapter is preferable to leaking
tenant models into a standalone module or quietly relaxing authorization.
Core stock arithmetic and business invariants remain in shared pure
`domain.py`; company-specific transactional operations remain in the
tenant application adapter.

## Verification

- Full catalog source (tenant mode): existing tenant and branch regression tests.
- Generated `--apps catalog`: owner-scoped Catalog API without Organizations.
- Generated `--apps inventory`: own InventoryItem/warehouse/stock API without
  Catalog or Organizations; idempotency and cross-owner checks.
- Generated `--apps inventory catalog organizations`: former tenant
  models, stock commands and IDOR regression tests.
- PostgreSQL row-lock tests in tenant mode, plus Docker and SeaweedFS CI.
