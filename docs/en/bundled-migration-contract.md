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
