# PrimaryKit documentation (English)

**Language:** English · [Русский](../README.md) · [Project home](../../README.md)

This is the English-language guide to the **implemented source catalog**, verified against the repository's `main` branch on 2026-10-18. The source version is `0.1.0`; a successful CI run is not a certification of an arbitrary generated client's production configuration.

## Read in order

1. [Quick start and migrations](getting-started.md)
2. [Module catalog, dependencies and URLs](modules.md)
3. [Architecture, ownership and compatibility](architecture.md)
4. [Implemented capabilities and feature limits](features.md)
5. [Operations and security checklist](operations.md)
6. [Project status and release readiness](project-status.md)

## Newly implemented module guides (#45–#52)

[Shared tenant permissions](tenant-permissions.md) · [Workflows](workflows.md) · [Tasks scheduler](tasks-scheduler.md) · [Device sessions](device-sessions.md) · [Usage quotas](usage-quotas.md) · [Chat / Realtime](chat-realtime.md) · [Privacy retention](privacy-retention.md) · [Module scaffold](module-scaffold.md)

## Reference documentation by topic

The following detailed documents are in the source-level `docs/` directory; some are in Russian, some in English. The English guides above describe the same current features.

| Area | Detailed source reference |
| --- | --- |
| Generator, CLI, onboarding | [Project generator](../project-generator.md), [module scaffold](../module-scaffold.md), [module upgrades](../module-upgrades.md), [project doctor](../doctor.md), [OpenAPI compatibility](../api-compatibility.md) |
| Independent clients | [Independent projects](../independent-projects.md), [manifest compatibility](../module-compatibility.md), [module development](../module-development.md) |
| Authentication / tenants | [Users](../users-architecture.md), [sessions](../device-sessions.md), [Organizations](../organizations-architecture.md), [RBAC](../rbac-architecture.md), [API keys](../api-keys.md) |
| Business contexts | [Catalog](../catalog-architecture.md), [Inventory](../inventory-architecture.md), [commerce](../commerce-architecture.md), [Storage](../storage-architecture.md), [Statistics](../statistics-architecture.md) |
| Async / integration | [Tasks and scheduling](../tasks-architecture.md), [Outbox](../outbox-architecture.md), [webhooks](../webhooks.md), [Celery](../celery-rabbitmq.md), [Chat / realtime](../chat-realtime.md) |
| Policies and utilities | [Workflows](../workflows.md), [usage quotas](../usage-quotas.md), [privacy](../privacy-retention.md), [idempotency](../idempotency.md), [CSV](../csv-exchange.md), [search](../search.md) |
| Runtime / operations | [Deployment](../deployment.md), [production operations](../production-operations.md), [Redis](../redis-cache.md), [rate limits](../rate-limiting.md), [observability](../observability.md), [HTTP integrations](../http-integrations.md), [feature flags](../feature-flags.md) |

Architecture decisions: [0001](../adr/0001-copy-based-modular-monolith.md), [0002](../adr/0002-storage-bounded-context-and-policies.md), [0003](../adr/0003-implemented-ddd-boundaries.md), [0004](../adr/0004-copyable-module-contract.md), [0005](../adr/0005-standalone-catalog-inventory.md).

## Documentation scope

Core onboarding, architecture, module coverage, production boundaries and release status are documented in **both languages**. Deep per-module references have not all been independently translated into English; do not assume the English index is a complete line-by-line translation. Code, tests and manifests are authoritative when documentation and implementation diverge.
