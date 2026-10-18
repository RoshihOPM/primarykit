# Implemented features and their limits

**Language:** English · [Русский: каталог модулей](../modules.md) · [English index](README.md)

This is a practical inventory of **merged code**, not a promise that every optional module is automatically enabled in a generated project.

## Identity, permissions, tenancy

- **Users:** JWT login/refresh, email verification and recovery, profile, owner-scoped device sessions, per-session/all-session revoke, password-change revocation. Refresh is revoked immediately; **already-issued access JWTs may remain valid until expiry** (five minutes by default).
- **Organizations:** memberships, branches, roles and reusable explicit tenant permission policy. Cross-tenant access must fail closed in the caller's queryset and service. Django superuser is not an implicit tenant override.
- **RBAC/Audit:** Django Groups and Permissions, immutable action records. Neither creates authorization automatically in arbitrary client business logic.
- **API Keys:** hashed, one-time-revealed, permission-bound scoped tokens with expiry/revocation. Issuance requires trusted client-owned decisions.

References: [sessions](../device-sessions.md), [Organizations](../organizations-architecture.md), [API Keys](../api-keys.md).

## General application primitives

- **Workflows:** framework-independent transition definitions with guards/permissions, optional PostgreSQL-backed transition history, version checks and row locks. Client owns aggregate schema and routes.
- **Idempotency:** PostgreSQL-backed command receipts for safe replay; not automatically wrapped around arbitrary HTTP endpoints or external side effects.
- **Usage Quotas:** immutable owner/tenant policies, explicit intervals, atomic PostgreSQL consumption and event ledger; not a subscription engine or billing gateway.
- **Privacy:** explicit per-client redact/anonymize/delete policies, dry-run, grace periods, legal hold, audited idempotent commands and optional Tasks execution. No automatic deletion or legal compliance guarantee.
- **Search, CSV, Feature Flags:** scoped PostgreSQL search, bounded CSV import/export protections and local opt-in flags. They cannot replace app-level access control.

References: [workflows](../workflows.md), [quotas](../usage-quotas.md), [privacy](../privacy-retention.md), [idempotency](../idempotency.md).

## Jobs, integrations and transport

- **Tasks:** PostgreSQL-backed queue and recurring scheduler with timezone/DST semantics, leader/worker leases and retry policy. Delivery is at least once, not exactly once. The scheduler is opt-in.
- **Outbox + Webhooks:** transactional business events, allowlisted delivery, HMAC inbound/outbound signing, replay protection; downstream consumers must deduplicate.
- **Celery / RabbitMQ / Redis:** explicitly selected optional transport, cache and distributed auth throttling. No mandatory broker in the minimal application.
- **Chat + Realtime:** private 1:1 HTTP messages, read receipts, owner/tenant authorization, scoped optional Storage attachments; WebSocket opt-in uses explicit access JWT and resume cursor. Per-connection PostgreSQL polling (~every two seconds) needs capacity planning; there is no automatic global broadcast subscription.
- **Observability + HTTP integrations:** request IDs, structured safe logs, trusted outbound HTTPS with restricted hosts/bodies/retries.

References: [scheduler](../tasks-architecture.md), [chat](../chat-realtime.md), [webhooks](../webhooks.md), [HTTP adapter](../http-integrations.md).

## Business module examples

- **Catalog/Inventory:** owner-only standalone and optional tenant schema; categories/SKUs/warehouses/reservations. Tenant mode must be chosen before migrations.
- **Orders/Sales:** price snapshots and user-scoped records. They do not perform authoritative server pricing, stock adjustment, fiscalization or multi-tenant sales.
- **Payments:** PaymentIntent plus privileged manual reconciliation only. Not connected to a payment service provider and not suitable for accepting real payments as-is.
- **Storage:** personal/organization-scoped private files, local/S3-compatible backends, explicit access policy.
- **Statistics:** auto-discovered metrics filtered to the authorized scope, not a general-purpose analytics warehouse.

References: [commerce](../commerce-architecture.md), [catalog](../catalog-architecture.md), [inventory](../inventory-architecture.md), [storage](../storage-architecture.md).

## Developer tooling

- Independently generated client projects with their own dependency lockfile.
- Presets, dry-run, offline project doctor and read-only module upgrade analysis.
- Offline OpenAPI compatibility checks for breaking contract changes.
- Source-only CLI for module scaffolding and JSON/DOT dependency visualization.

References: [project generator](../project-generator.md), [scaffold](../module-scaffold.md), [API comparison](../api-compatibility.md).

**Non-goals:** built-in generic CRM UI, production-ready payment processing, turnkey multi-tenant e-commerce, zero-downtime deployment automation, or automatic source upgrades of external projects.
