# PrimaryKit roadmap — implemented modules and next milestones

Updated: 2026-10-17. This is a future-improvement backlog, **not** a list of unimplemented modules.

## Already implemented (v1)

| Context | Current capabilities | Documentation |
| --- | --- | --- |
| Core, Users, Notifications | Project infrastructure, JWT, email flows | [Users](users-architecture.md) |
| Organizations, RBAC, Audit | Memberships, branches, permissions, immutable audit | [Organizations](organizations-architecture.md) |
| Storage | Owner / optional organization scope, S3/SeaweedFS | [Storage](storage-architecture.md) |
| Catalog | Categories, SKUs, typed attributes; standalone/tenant modes | [Catalog](catalog-architecture.md) |
| Inventory | Warehouses, reservations, stock ledger, idempotency; standalone/tenant modes | [Inventory](inventory-architecture.md) |
| Tasks | Internal PostgreSQL queue, retries, leases and separate worker | [Tasks](tasks-architecture.md) |
| Outbox / Webhooks | Transactional events and HMAC-signed webhook transport | [Webhooks](webhooks.md) |
| Rate Limit / Observability | Shared Redis auth throttling, request IDs and JSON access logs | [Observability](observability.md) |
| Feature Flags | Local, deny-by-default release toggles; no remote or database dependencies | [Feature Flags](feature-flags.md) |
| Search | Explicitly owner/tenant-filtered PostgreSQL full-text search helper | [Search](search.md) |
| CSV Exchange | Strict, bounded CSV import validation and formula-safe export primitives | [CSV Exchange](csv-exchange.md) |
| API Keys | Scoped personal credentials, expiration and revocation | [API Keys](api-keys.md) |
| Idempotency | Durable per-principal, per-operation PostgreSQL deduplication | [Idempotency](idempotency.md) |
| HTTP Integrations | Trusted outbound HTTPS with bounded responses and retries | [HTTP Integrations](http-integrations.md) |
| Cache | Django cache facade and optional Redis backend | [Cache](redis-cache.md) |
| Celery Tasks | RabbitMQ broker, optional Redis result backend, copyable worker adapter | [Celery](celery-rabbitmq.md) |
| Statistics | Auto-discovered providers, scoped counts and date windows | [Statistics](statistics-architecture.md) |
| Orders | Owner-private priced order snapshots and cancellation | [Commerce](commerce-architecture.md) |
| Sales | Owner-private sale records, optional verified order links and voiding | [Commerce](commerce-architecture.md) |
| Payments | Payment intents and superuser-only manual reconciliation (no real gateway) | [Commerce](commerce-architecture.md) |

For the full source-code/module contract, use [Repository Guide](repository-guide.md) and [Module Catalog](modules.md).

## Priorities for v2

### 1. Trustworthy e-commerce checkout

- Price calculation on the server from a trusted product/price source; taxes, discounts, coupons, shipping costs and controlled rounding.
- Consistent reservation of Inventory for Orders, expirations and compensation after cancellation; explicit idempotent commands and transactional guarantees.
- Tenant-ready Orders/Sales/Payments models: owner organization, seller/manager access, branch restrictions, customer visibility and audited permissions.
- Order and Sale statuses that distinguish accepted, fulfilled, canceled, refunded or partially fulfilled with terminal-state invariants.

### 2. Real payment provider adapters

- Verified signed webhooks per provider, provider account/transaction identity and durable event inbox; protect against spoofing and replay.
- Partial/full refunds, chargebacks, payment retries, ledger reconciliation and failure recovery.
- Proper support for payment currencies, precision/rounding, multi-currency reporting and payment-provider-specific statuses.
- Integration and sandbox end-to-end tests before enabling real money operations.

### 3. Scaling and historical analytics

- Currency-specific grouped financial aggregates (never sum different currencies into one unlabelled number).
- Historical inventory balance charts from immutable StockMovement and period boundaries.
- PostgreSQL indexes/query budgets, dashboard widget metadata, caching after measurements.
- Async aggregation, transactional outbox and materialized reports only when justified by real traffic.

### 4. Catalog/Inventory future needs

- Localization and fallback rules for product names/descriptions (en/ru/ko).
- Product variants and category-specific attribute indexing, full text/search integration.
- Lots/serials, multiple units, costing rules, warehouse locations, backdated operations and offline sync.
- Explicit optional Catalog-to-Inventory SKU mapping and data migrations between pinned standalone/tenant schemas.

### 5. Operational robustness

- Stronger shared throttling for public login, endpoints, tracing/metrics/alerts and restored backup testing.
- Durable task queues, notifications/outbox and idempotent reconciliation for external side effects.
- Module compatibility and reviewed manual upgrades are documented; automate diff reports only when they cannot overwrite client changes.
- Future work: organization-bound API credentials, dedicated authenticated issuance APIs and performance tuning with real workloads.

## Definition of done for new modules

Each feature must define a bounded context, explicit optional dependencies, secure scope, domain invariants, transactional application commands, tested migrations, API/schema contract, negative IDOR and concurrency tests (when relevant), generated-project smoke, documented production limitations, and green CI. Passing a mocked provider test does **not** replace a real provider sandbox test.
