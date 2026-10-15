---
name: system-architect
description: Design or review a Django/DRF backend architecture, module boundaries, API contracts, scalability, reliability, security, and ADRs. Use before cross-module features, integrations, infrastructure or service design.
---

# System Architect for PrimaryKit

Use this skill for proposed features that change boundaries, APIs, permissions, infrastructure, or data flows. Follow the policies in the repository's `AGENTS.md`. Read `docs/architecture.md` and `docs/core-conventions.md`.

## Procedure

1. Restate the use case and constraints: actors, throughput, data volume, SLA, multi-tenancy, consistency, delivery deadline, rollout risk.
2. Map entities and responsibilities to Django apps. Start with a modular monolith; justify extra services only with a measurable need.
3. Define the public interface: URL and API version, request/response schema, validation, auth/RBAC, permissions, idempotency, error and pagination contracts.
4. Identify transaction boundaries and failure paths, timeouts, retries, duplicate delivery, outbox/eventual consistency (only if needed), audit logging, and observability.
5. Identify query patterns and storage requirements; engage `database-architect` skill when models, concurrency, migrations or expensive queries change.
6. State at least two choices with concrete trade-offs: complexity, coupling, operational burden, performance, developer effort, and reversibility.
7. Propose implementation sequence and verification: unit, API, integration, concurrency and migration tests, deployment/rollback.
8. Record material decisions as an ADR under `docs/adr/`. For small features, provide a brief decision log instead.

## Default design rules

- Keep Core minimal. Business logic stays in feature modules; use `services` for nontrivial operations and `selectors` for reusable complex reads.
- Prefer DRF generic views / ModelViewSet for ordinary CRUD and avoid invented layers.
- Avoid an all-purpose Product model for every domain. Separate catalog attributes from business-specific entities.
- Authorization is server-side, object-aware, deny-by-default; avoid unrestricted serializers and mass assignment.
- PostgreSQL is the source of truth. Cache and queues are opt-in and cannot be relied on for transactional correctness.
- Plan for operations: health checks, structured logs, safe deploys, backup and restore, monitoring and limits.

## Deliverable

Provide: scope/non-goals; component diagram or flow; data ownership; API/auth contract; failure/concurrency handling; choices and trade-offs; rollout and testing; unanswered risks. Never assert performance characteristics without measurements.

For detailed checks see [review checklist](references/review-checklist.md).
