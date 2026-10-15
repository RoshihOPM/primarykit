# ADR 0001 — Copy-based modular Django monolith

Status: Accepted (starter design)

## Context

PrimaryKit is a personal source catalog for starting new backend projects, not a versioned shared library and not a hosted multitenant SaaS. Reuse must be fast while deployments, business entities, and migration histories remain separate per client.

## Decision

- Build a plain Django/DRF project in `config/` with reusable Apps in `apps/`.
- Copy a selected set of Apps into a new repository. Maintain the new project's migrations **in that project**.
- Keep core utilities small; project-specific rules and integrations belong in business Apps.
- Use Django ORM, DRF generic views and standard mechanisms before introducing services, queues, Redis or microservices.
- Use agent skills for reviewable design and verification, but GitHub CI and human review are release gates.

## Alternatives

1. Shared installable packages: easy centralized upgrades but create compatibility/migration coordination across client projects. Reconsider when modules stabilize and upgrades dominate work.
2. Single multi-tenant backend: strong reuse but client isolation, operations and SLA coupling are unwanted for now.
3. A separate service per module: independent scale but higher deployment/consistency costs; not justified for the anticipated workloads.

## Consequences

Duplicated source and security fixes require deliberate propagation. Some shared modules may diverge per client. Measure this overhead and revisit packaging only once reuse patterns are mature.
