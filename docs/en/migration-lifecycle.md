# Ownership and lifecycle of module migrations

PrimaryKit copies modules into independent Django projects. Existing clients
own their applied migration graphs and data; no source upgrade may silently
rewrite or fake their applied revisions.

## Manifest contract

Each `apps/<module>/manifest.py` declares `migration_policy`:

- `none`: no module-owned schema (default).
- `client`: the generated client creates, reviews and commits its migrations.
- `bundled`: the source ships a reviewed, committed migration history for **new**
  clients, which the generator preserves without regenerating that baseline.

The source currently pilots `bundled` with `tasks/0001_initial.py`.
This does **not** imply that an older client with independently generated
Tasks migrations can safely adopt the new source history.

## Compatibility boundaries

Catalog and Inventory each support standalone and tenant model families. The
selected profile is pinned at generation. Do not change profiles or copy a
tenant migration into an existing standalone database. A fresh schema and a
historical migrated client are distinct upgrade cases.

The generated PostgreSQL CI matrix tests fresh schema creation, repeat migrate
and persisted sample records for selected modules. It does **not** demonstrate
safe upgrades from historical published versions.

## Safe assessment workflow

```bash
python -m apps.core.migration_plan
python scripts/migration_adoption.py --source . --project ../client-api
# Optional, explicit DB ledger inspection; run with a read-only DB user.
DATABASE_URL=postgresql://... python scripts/migration_adoption.py \
  --source . --project ../client-api --verify-postgres --strict
```

The adoption inventory is read-only: it compares file hashes, pinned schema
profiles and optionally the PostgreSQL `django_migrations` ledger. Even a
matching ledger does not certify physical table structure or data safety.

For #88, remaining work includes versioned, separately reviewed migration
histories, dependency-graph review, data-preserving historical PostgreSQL
upgrade tests and `makemigrations --check --dry-run`. Squawk SQL lint is already
run in CI, but manual review of data changes and table locks remains mandatory.

Never overwrite applied client migration files or use `--fake` to bypass
unverified schema differences. See [bundled migration contract](bundled-migration-contract.md)
and [issue #88](https://github.com/RoshihOPM/primarykit/issues/88).
