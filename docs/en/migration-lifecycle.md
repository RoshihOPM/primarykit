# Module schema ownership and upgrade roadmap

PrimaryKit is a **copy-based** generator. Existing clients own migrations and data.
This document describes the current behavior, **not bundled migrations**.

## Current manifest contract

Each module declares `migration_policy` in its `manifest.py`:

- `none` (default): the module has no client-owned database schema.
- `client`: a generated client creates and commits its own migrations.

The generator and generated CI now derive migration labels from the installed
manifests. Run `python -m apps.core.migration_plan` to inspect the list.

## Compatibility boundary

The source catalog **does not yet ship reusable migration histories**. Never
remove, rename or overwrite existing client migration histories during an update.
Catalog and Inventory support different standalone and tenant schemas selected
before the initial migration. A single bundled migration graph is not safe
without resolving these mode-dependent schemas first.

## Milestones for versioned migrations

1. Freeze base schemas, document foreign-key dependencies, and establish
   a standalone/tenant schema policy.
2. Add reproducible catalog-owned initial and incremental migration histories.
3. Exercise clean generation plus upgrades from migrated projects with real
   persisted data, and run `makemigrations --check --dry-run` in CI.
4. Add PostgreSQL migration safety lint and review online data migrations.
5. Keep existing client-generated histories on a documented manual migration
   review path until adoption is proven safe.

Never automatically apply schema-changing module upgrades without review.
