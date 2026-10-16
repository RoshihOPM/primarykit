# ADR 0003 — DDD-lite boundaries for implemented PrimaryKit modules

Status: Accepted (2026-10-16). Replaces ad-hoc service-only conventions; extends ADR 0001/0002.

## Context and non-goals

PrimaryKit copies Django apps into separately deployed client repositories. It must
support small CRUD services without boilerplate and business-heavy contexts with
testable invariants. We will **not** introduce microservices, an ORM repository
wrapper, cross-service events, CQRS, a generic unit-of-work, or domain events
without a concrete use case.

## Decision: bounded contexts, not arbitrary layers

Each business app is the unit of ownership and deployment *within a generated
modular monolith*. Contexts own their models, queries, commands and rules:

| Context | Owns | Key invariant / domain module |
| --- | --- | --- |
| Users | account identity, tokens, recovery | account lifecycle and email eligibility |
| RBAC | Django Group permission assignments | allowlisted permission identities, role deletion |
| Organizations | company, membership, invitations, branches | role-management policy, last active owner |
| Catalog | categories, typed attributes, SKUs | typed validation and normalization |
| Inventory | warehouses, reservations, balances, ledger | stock transitions, reservation state, command shape |
| Storage | private file metadata and object keys | owner policy with optional organization adapter |
| Audit | immutable security/business event snapshots | snapshot PII/secret redaction constraints |
| Notifications | sending templated emails | immutable email intent, outgoing gateway port |

`domain.py` contains **pure Python** value objects, decisions and invariant
functions: no Django, DRF, SQL, HTTP, repositories or imported code from
another PrimaryKit bounded context. Domain failures are plain exceptions.

`services.py` and similar command handlers form the **application layer**.
They orchestrate ORM reads, locks, transactions, policy rechecks, audit events
and integrate domain rules. DRF serializers/views and Django admin implement
**incoming adapters**; they translate domain errors into HTTP validation errors.
Django models/ORM, S3 storage and Django MAILERS are **persistence/outbound
adapters**. They may remain in the app root while simple modules stay small.

Cross-context calls are explicit. Core stays infrastructure-like; it does not
own business policies. Storage's Organizations integration lives in
`apps.storage.policies` and is optional, not a hard model foreign key. Audit
has an optional facade in Core. Notifications exposes an outgoing
`EmailGateway` Protocol and a concrete Django adapter.

## Dependency rules

- Domain never imports framework code or another context. Enforced by
  `apps/core/tests/test_ddd_boundaries.py` (also runs in generated projects).
- Application may depend on its **own** domain and on explicitly required
  context public services/policies. Do not import another context's views,
  serializers or admin classes.
- Incoming adapters call local application services for nontrivial commands.
  They do not duplicate stock or role invariants.
- `Inventory -> Catalog + Organizations`; `Catalog -> Organizations`;
  `Users -> Notifications`; `Storage -> Organizations` only via optional
  adapter. Other context access is deliberate, not an implicit dependency.
- The same critical invariant is validated on service execution even when a
  serializer has already checked it: APIs are not the only callers.
- No accidental `is_superuser` bypass across organization boundaries.

## Data, consistency and security

- Django migrations remain owned and versioned in the generated project.
  This refactor does not alter models, API routes or DB schema.
- PostgreSQL remains source of truth. Inventory movement/ledger writes,
  reservation changes, company membership updates and file metadata changes
  are transactional, retain their existing row locks and idempotency checks.
- Domain validation alone is **not** an authorization boundary. Scope querysets,
  foreign keys and service commands. Do not move tenant checks into client data.
- Audit failure still rolls back business mutations when inside atomic().
  Sending email/objects remains an external side effect; asynchronous outbox
  reliability is separate future work.

## Migration and evolution

This is an incremental, behavioral-preserving refactor. Existing API imports
continue to use `services.py`; legacy code can move into application packages
only when complexity merits it. Avoid empty `domain/`, `application/` and
`infrastructure/` directories created solely for naming.

For a new business feature:

1. Identify the owning context and cross-context contracts.
2. Specify pure invariants and value objects with tests.
3. Implement orchestration in services with explicit transactions/locks.
4. Add ORM persistence and external adapters.
5. Add DRF endpoints, negative permission/IDOR tests and integration checks.
6. Re-check generator dependencies and generated-project smoke tests.

## Trade-offs

ORM models still serve as persistence models rather than separate domain
entities. This is intentional pragmatic DDD for a Django monolith. Some role
and query policies still live in application or adapter code for safety; we
have *not* implemented exhaustive Evans-style aggregates, event sourcing,
a messaging bus or a universally enforced interface boundary. Revisit only
where business complexity, team size or real integration needs justify cost.
