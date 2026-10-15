# Catalog, inventory and i18n — design backlog (not implemented)

## Proposed independent Apps

### catalog

`CatalogItem` has stable properties (UUID, SKU where applicable, name, description, status, category). Domain-specific car/product/warehouse features do **not** belong directly on its base model.

For changing attributes consider `AttributeDefinition` (name, type, unit, required, filterable), type-safe `AttributeValue` and a translation entity for localized display. Prefer native columns and indexes for high-cardinality filters and mandatory invariants; JSONB is an option for low-query-flexible metadata, not a default for the full catalog.

Questions before implementation: catalog vs listing vs physical SKU, identity uniqueness across tenants, product variants, search/index strategy, translations/fallbacks, lifecycle and pricing.

### inventory

Suggested entities: `Warehouse`, `StockLocation`, `StockItem`, `StockMovement`, `StockBalance`, `StockReservation`. Inventory operations should have explicit service contracts such as Receive, Transfer, Reserve, Release and WriteOff.

Movements are an immutable audit/ledger; balance is a transactional materialization for fast reads. Do not mutate stock by read-modify-save. Use conditional atomic UPDATE or row locks with stable order, enforce nonnegative available stock where required, idempotency keys and consistent movement/balance updates in `transaction.atomic`.

Questions before implementation: unit of measure, lots/serials, negative stock allowed or not, available/on-hand/reserved definitions, reserved expiration, inventory costing, backdating, offline clients and concurrent writers.

### Localization

Infrastructure is enabled in Core for en/ru/ko. Dynamic catalog content will need explicit localized models and fallback policy; no field-per-language schema assumption.

## Review gates

Each business module needs an ADR or equivalent documented design, API contract, permissions, migrations, unit/API/PostgreSQL integration and concurrent-write tests. Do not claim implementation of catalog or inventory until these gates are met.
