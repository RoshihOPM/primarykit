# Architecture and ownership

**Language:** English · [Русский](../architecture.md) · [English index](README.md)

## What the kit is

PrimaryKit is a **copy-based modular Django monolith starter**. It consists of `config/` (Django settings/entrypoints), portable apps under `apps/`, developer CLIs in `scripts/`, and optional Compose deployments. It is not a shared runtime dependency, hosted product or code-synchronized fleet.

```text
PrimaryKit source checkout
  scripts/new_project.py
  apps/core + users + notifications + selected modules
          |
          | copies selected source, manifests and compatible setup
          v
Generated client repository
  Django/DRF API + PostgreSQL + client-owned migrations
  Client business logic, policies and releases
  Optional Redis / Celery / WebSocket / S3
          X no runtime dependency on the PrimaryKit checkout
```

## Module contract

The `apps/<name>/manifest.py` declares required modules, optional integrations and registration metadata. The generator resolves hard dependency closure and makes a detached copy. Copies automatically register installed app configs and root URLs when a module defines routes. A missing required dependency must fail rather than silently degrade.

Implement **business decisions** in `domain.py` where non-trivial invariants exist, without Django/DRF/ORM imports. Use `services.py` for transaction orchestration and authorization; `models.py`, `views.py`, `serializers.py` and gateways are adapters. Avoid unused DDD scaffolding for basic CRUD.

## Security model

Authorization belongs to every owner/tenant-sensitive action: restrict list/detail querysets, verify object ownership and related foreign keys in services, guard writes with appropriate transactions and deny cross-scope IDOR. A shared Organizations policy **can be reused** by client code; it is not a global permission bypass or magic multi-tenant switch. A superuser must not implicitly access all tenant data.

For monetary, stock, quota, JWT refresh, legal-hold, and workflow transitions: consider concurrent actors and PostgreSQL locking semantics. A unit test with SQLite alone does not establish row-lock safety.

## Migration and upgrade ownership

The source catalog intentionally ships **model definitions but not reusable Django migration histories**. On first generation, choose modules and Catalog/Inventory schema modes, run `makemigrations`, review, run `migrate`, and commit **generated-client migrations**. Never delete old client migrations or change modes without a reviewed migration strategy.

There is no background upgrade agent. Source changes must be reviewed for every generated client with the offline upgrade report, optional OpenAPI contract diff, release plan and deployment tests.

## Operational composition

PostgreSQL is the baseline source of truth. Redis is optional caching/rate-limiting, not authority for permissions/paid quotas. PostgreSQL Tasks is a durable queue with opt-in scheduling and lease fencing; Celery/RabbitMQ is an **independent optional adapter**. Outbox delivers events at least once; consumers deduplicate effects. Chat transport defaults to HTTP; opt-in WebSocket uses ASGI and polling. Local file storage is not a shared HA filesystem; use private S3-compatible storage for scaled deployments.

## Limits of provided business modules

Orders/Sales/Payments are owner-scoped sample contexts. They lack automatic cross-context stock deduction, server-authoritative checkout pricing, real acquirer integration, refunds and tenant-level commerce. Do not market them as ready-to-use financial infrastructure. A project using them still needs product-specific access policies, migrations, accounting and integration tests.

See source [ADRs](../README.md#архитектурные-решения), [independent project rules](../independent-projects.md), [module compatibility](../module-compatibility.md) and [production operations](operations.md).
