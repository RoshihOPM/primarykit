# ADR 0002 — Storage as a bounded context with optional tenancy

Status: Accepted for PrimaryKit source catalog (2026-10-16).

## Context

PrimaryKit copies selected modules into standalone Django projects. The earlier
Storage model required Organizations, so even a single-user API had to install
companies, memberships and invitations. This is feature coupling, not DDD.

## Decision

- Storage owns file metadata, uploads, downloads and its own invariants.
- It references the owner from required Users; it stores the optional
  organization identity as a nullable UUID, not a ForeignKey to another context.
- Application-layer `apps.storage.policies` defines the FileScope port. With
  no organization ID, only the file's owner may list, read, download or delete.
- When Organizations is installed and an organization URL is used, its adapter
  resolves an active membership and owner/admin role. No global superuser bypass.
- Service commands revalidate policy under a transaction (and company row lock
  for tenant writes); they do not trust viewset checks or incoming file metadata.
- A personal URL always filters organization_id IS NULL; a tenant URL always
  filters that organization's UUID, never both.
- Generator selects Organizations only for modules that truly need it.
  `--apps storage` is standalone; selecting both adds scoped tenant routes.

## Boundaries and trade-offs

This is pragmatic DDD: bounded contexts, a stable identity reference and an
access-policy port, **not** full CQRS, an event bus or ubiquitous repositories.
The opaque organization reference intentionally avoids a database FK, so a
deleted organization can leave historical tenant file metadata. The application
must preserve its ACL even after organization deactivation; tenant access
always fails closed. A future auditable retention/purge workflow may reconcile
orphans, and a privileged repair path must not expose company files via personal
routes. Do not replace this with generic `is_superuser` checks.

A copied client's migration history belongs to that client. Replacing the old
FK with an opaque UUID requires an explicit data migration for populated
clients. Choosing personal vs tenant attachment is **not** inferred from user
membership; caller intent is explicit in route or trusted service arguments.

## Verification

- Standalone `--apps storage` passes Django checks, migrations and owner-IDOR
  tests without importing Organizations.
- Multi-tenant source and generated systems retain cross-company IDOR,
  membership revocation, transactional rollback and real SeaweedFS coverage.
- Ruff, Python tests, PostgreSQL smoke and generator CI are release gates.

## Future boundaries

Catalog/Inventory may be separated further when real reuse requires it.
Avoid shared `utils` containing business policy. Add a domain/application/
infrastructure split inside a module only where complexity justifies it.
