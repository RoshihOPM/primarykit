# Catalog v0.1 — universal products without one-table-to-rule-them-all

`catalog` is an opt-in **independent Django app**. It does not imply inventory, listing advertisements, price calculation or tenancy.

- `Category`: UUID, unique slug, name, active flag.
- `AttributeDefinition`: typed `code`, category, type (text / integer / decimal / boolean), required flag.
- `CatalogItem`: UUID, canonical SKU, category FK, name, description, typed/validated `attributes` JSON and active flag. Never use client-provided owner or permission fields.

The public surface is authenticated reads; writes require active superuser. API endpoints:
`/api/v1/catalog/categories/`, `/api/v1/catalog/attributes/`, `/api/v1/catalog/items/`. Only GET/POST/PATCH, no DELETE; deactivate items instead. Attributes definitions can be created but not changed via the API (changing definitions would invalidate existing items). Users without admin privileges cannot read inactive categories/items. Reads support category slug and exact SKU filter.

Attribute definitions live in relational tables. Typed values are kept in JSON as flexible catalog metadata; monetary or heavily-filtered domain fields should become indexed SQL columns in the consuming project. Item create and update validates attributes against definitions; no per-attribute custom SQL indexes or translations are supplied in v0.1. Changing a category's schema while items exist requires a data migration / explicit validation of existing items; no automatic retroactive revalidation.

Catalog doesn't contain price or inventory counts. These belong in domain-specific sales or the separate Inventory app. Inventory may optionally reference `CatalogItem` while preserving separate implementation boundaries.

Audit event writes are part of the same transaction as API writes if Audit is installed. An explicit `CatalogAccess` permission restricts writes to superusers, and queryset filtering prevents inactive item leakage. No arbitrary per-object ACL and no tenant-scoped catalog in this generic baseline.

Migration policy: generate and commit a new catalog migration **in each independent generated client repository**. CI generates migration artifacts for tests only.
