# Portable module catalog

**Language:** English · [Русский](../modules.md) · [English index](README.md)

The repository has **33** source apps in `apps/` at the reviewed commit (2026-10-18). The baseline copied into every generated project is **core + users + notifications**. All others are optional; however, individual modules have **hard dependencies** that the generator resolves.

| Module | Included behavior | Hard dependencies | Optional integrations |
| --- | --- | --- | --- |
| `core` | Conventions, registry, health checks, doctor | — | — |
| `users` | JWT + email accounts, verification, recovery, personal device sessions | core, notifications | audit |
| `notifications` | Email transport and templates | core | — |
| `organizations` | Companies, branches, memberships, shared tenant access policy | users | audit |
| `rbac` | Django Groups and Permissions | users | — |
| `audit` | Immutable action log | users | — |
| `api_keys` | Scoped, hashed owner credentials with expiry/revocation | users | audit |
| `storage` | Private personal and optional organization files; local/S3 | users, core | organizations, audit |
| `catalog` | Categories, SKUs, typed attributes; standalone or tenant schema | users | organizations, audit |
| `inventory` | Warehouses, stock movements, reservations | users | catalog, organizations, audit |
| `orders` | Owner-scoped order snapshots and cancellation | users | catalog, sales, payments, audit |
| `sales` | Owner-scoped sale records and voiding | users | orders, payments, inventory, audit |
| `payments` | PaymentIntent and superuser-only manual reconciliation | users | orders, sales, audit |
| `statistics` | Authorized, discovered metrics and aggregation | users | catalog, inventory, storage, organizations |
| `feature_flags` | Deployment-local opt-in flags, off by default | core | — |
| `search` | Explicitly scoped PostgreSQL full-text search helper | core | — |
| `csv_exchange` | Size-limited CSV input / formula-safe output | core | — |
| `idempotency` | Durable command replay receipts in PostgreSQL | core | — |
| `http_integrations` | Trusted allowlisted HTTPS requests and bounded retries | core | — |
| `workflows` | Pure state rules, guarded transitions, optional transition history | core | audit, outbox |
| `usage_quotas` | PostgreSQL owner/tenant quotas with idempotent usage events | users | organizations, statistics |
| `privacy` | Client-controlled redaction/anonymization/delete execution policies, holds | core, audit, tasks | — |
| `tasks` | PostgreSQL work queue, retries, leases, opt-in recurring scheduler | core | — |
| `outbox` | Transactional event recording and at-least-once dispatch | core, tasks | — |
| `webhooks` | Signed inbound and durable outbound notifications | core, outbox | — |
| `cache` | Optional native redis-py cache client | core | — |
| `rate_limit` | Shared Redis auth throttling across workers | core, cache | — |
| `celery_tasks` | Optional Celery worker adapter / RabbitMQ broker | core | — |
| `observability` | Request IDs and safe structured HTTP logs | core | — |
| `chat` | Scope-safe 1:1 conversations, messages, read receipts, attachments | users | organizations, storage, realtime |
| `realtime` | Opt-in ASGI WebSocket authenticated event transport | users | chat |
| `favorites` | Authenticated bookmarks and bounded private saved searches | listings | — |

The hard/optional columns describe **manifest dependencies**; each optional integration can require additional configuration and schema choices. For the authoritative manifest contract, inspect `apps/<name>/manifest.py`.

## Routes and non-HTTP modules

| Feature | Selected URL prefix / API |
| --- | --- |
| Account and authentication | `/api/v1/` |
| Personal files | `/api/v1/files/` |
| Organizations | `/api/v1/organizations/` |
| Standalone Catalog | `/api/v1/catalog/` |
| Standalone Inventory | `/api/v1/inventory/` |
| Orders, Sales, Payments | `/api/v1/orders/`, `/api/v1/sales/`, `/api/v1/payments/` |
| Manual payment reconciliation | `/api/v1/admin/payments/` (superuser) |
| Statistics | `/api/v1/statistics/` |
| Listing favorites / saved searches | `/api/v1/favorites/`, `/api/v1/saved-searches/` |
| Private chat | `/api/v1/chats/` |
| WebSocket for one dialogue | `/ws/v1/chats/{dialogue_id}/` (opt-in) |

Organizations + tenant modes use scoped organization URLs for Catalog and Inventory. Sessions use `/api/v1/users/me/sessions/`, `/api/v1/users/me/sessions/revoke-all/`, auth refresh and logout endpoints. See [device sessions](../device-sessions.md).

**No public HTTP CRUD endpoint is automatically exposed** by Workflows, Usage Quotas, Privacy Retention, Tasks, Outbox, Redis, Celery or the CLI scaffold. Those features are invoked by trusted client-owned application code.

## Important integration boundaries

- `catalog` / `inventory`: schema mode `standalone` or `tenant` is pinned **before first migration**. Tenant Inventory requires Catalog + Organizations. Conversion later needs a real data migration.
- `organizations` does **not** make Orders, Sales or Payments multi-tenant; those remain owner-scoped.
- `sales` does **not** update Inventory automatically; `payments` does **not** collect real money.
- `chat` requires its participants to be authorized on every request. WebSockets require explicit settings and an ASGI server; PostgreSQL polling is not a high-scale pub/sub solution.
- `usage_quotas` stores trusted limits in PostgreSQL, not Redis. The consuming client must authorize the underlying business action.
- `privacy` executes only explicit client handlers and never provides blanket cascade deletion.
- `tasks` and `outbox` have at-least-once processing; external effects must be idempotent.
- `feature_flags` do not confer permission; `api_keys` do not create globally privileged users.

See [implemented feature guide](features.md) and [full source references](README.md). Build your client's permissions and business models explicitly.

## Classified ads

Optional `listings` supports public moderated advertisements, privately owned drafts, staff-managed taxonomy and a disabled-by-default, private, moderated photo adapter. `favorites` adds private bookmarks and saved searches. No Catalog SKU/Inventory relation. See [Listings](../listings.md).
