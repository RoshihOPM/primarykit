# Opt-in bundled migration contract

The registry accepts three explicit per-module migration policies:
- `none`: this app has no DB schema.
- `client`: copy models without source migrations, then create/commit project-owned
  migrations (existing PrimaryKit behavior).
- `bundled`: preserve the module's reviewed and committed `migrations/` history
  during new-client generation, and do not regenerate its baseline initial migrations.

The generator **rejects** a bundled module whose source migration history is
missing. This avoids silently creating different migration origins.

**Pilot:** `tasks` ships a reviewed immutable `0001_initial.py` migration for new generated clients. Clients with an existing Tasks migration graph must keep their own history and use reviewed adoption.
Before enabling it for an actual module, publish a stable baseline, test
cross-application dependencies and PostgreSQL migrations, and establish an
adoption path for existing databases that already have independently generated
histories. In particular, Catalog and Inventory have distinct standalone/
tenant ORM models: never copy one mode's migrations to the other.

Existing client projects remain on their own migration history. Do not
manually rewrite applied migration files or assume `--fake` is safe.

## PostgreSQL state retention smoke

The generated-client PostgreSQL matrix now persists a real Tasks row after
`migrate`, repeats `migrate --noinput` and asserts the row is unchanged.
The `tasks`, `crm` and `all` matrix combinations verify the shipped Tasks
`0001_initial` history is idempotent on an existing database. Mode-specific
Catalog/Inventory model families remain covered by the independent `commerce`
(standalone) and `all` (tenant) fresh-client matrix cases.

**Not yet covered:** applying a newer bundled migration to an *older*
independently generated client, data-preserving cross-version upgrades or all
mode-specific source histories. Those require reviewed migration adoption,
releases and PostgreSQL fixtures before Issue #88 may be closed. Do not copy
source migrations over a client's applied migration files or use `--fake`
as a shortcut.

## Read-only client adoption inventory

From a trusted source kit checkout, inspect a client's existing migration files:

```bash
python scripts/migration_adoption.py --source . --project ../customer-backend
```

The report inventories bundled histories (currently Tasks), distinguishes
identical copied files from histories requiring review and rejects drift from
pinned Catalog/Inventory schema profiles. It does not import module code,
modify project files or database tables. An identical file history **does not**
prove the migrations were applied safely: compare the actual
`django_migrations` table, model state, FK edges and persisted data before
approving any adoption. Never replace historical client migrations.
