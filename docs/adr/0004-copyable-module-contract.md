# ADR 0004 — Portable Django module manifests and safe dependency installation

Status: Superseded in part by ADR 0005 (2026-10-16).

## Goal and boundaries

Enable **folder-based activation** for an existing Django project produced by
PrimaryKit: copying a self-contained app to `apps/<module>/` adds its
`INSTALLED_APPS` entry and route declarations automatically upon restart.
No custom project root settings or URL edits, no central module whitelist.

This does not make an existing PostgreSQL schema magically portable: migrations
must be generated, reviewed, committed and applied in each new client project.
Python packages, environment variables and services like S3/SMTP require
explicit provisioning. Never auto-apply schema changes in AppConfig.ready().

## Manifest contract

Each app provides `manifest.py` defining `Module(name, requires, optional,
routes, priority)` from `apps.core.module_registry`. Core loads manifests from
trusted on-disk `apps/` packages, verifies their names, topologically sorts
required dependencies, detects cycles and refuses missing hard dependencies.
`config/settings/base.py` and `config/urls.py` use this registry; optional
route integration is activated only if its prerequisite module is present.

- `required` means a hard code/schema dependency, not a deployment preference.
- `optional` is a declared integration; adapter imports must stay lazy and
  calls must deny access when the integration is absent.
- Route prefixes remain explicit; registering a module must not accidentally
  introduce unscoped tenant endpoints.
- A manifest is executable trusted Python in the same repository; do not install
  or copy source from unknown parties without review.

## Bundles vs truly independent modules

**Standalone on the PrimaryKit baseline:** Storage, Audit, RBAC, Organizations,
Notifications and the Users context. Storage adds tenant file routes only when
Organizations is present; it does not require Organizations to run.

**Mode-specific integrations:** Catalog and Inventory are standalone by default in
new standalone client projects (ADR 0005). Their tenant adapters still require
Organizations (and Catalog for Inventory) when explicitly selected prior to
initial migrations. `python manage.py install_kit_module inventory
--source ../primarykit` stages and copies the full dependency set from a
trusted checkout, preserves existing modules and reports the next migrations.
A raw copy of only Inventory fails fast with a missing dependency diagnostic.

For full Inventory independence, an **additional design** is needed: its own
inventory-item identity / warehouse ownership, optional Catalog and
Organizations adapters, a versioned migration plan and security acceptance
tests. Silently dropping tenant FK checks is forbidden.

## Stability, install workflow, security

- Module names are validated; dependency closure/cycle errors are explicit.
- The installer reads dependency fields with AST literal parsing (not executing
  foreign manifests), stages source folders before installation and doesn't
  overwrite existing app directories.
- Runtime discovery imports only installed, trusted module manifests. Empty or
  malformed manifests fail startup; accidental missing declarations must not
  silently skip apps.
- The generator uses the same manifest closure, removes unselected folders,
  and retains independent deployment/committed migration history.
- API contracts, tenant access, idempotency and existing DB schemas are
  unchanged by this registration architecture.

## Test gates

Unit tests cover discovery, routes, missing dependencies, cycles, copied
bundles and safe failures. CI must test generated audit-only, storage-only,
organization-only and inventory-bundle projects, plus PostgreSQL and SeaweedFS.
Test the **actual generated project**, not just the source catalog.
