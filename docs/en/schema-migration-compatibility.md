# Schema profile lock and migration adoption (#88)

A generated client owns its Django migration graph. Catalog and Inventory have
**two distinct** model families: `tenant` and `standalone`. Changing either
setting on a live client can silently change the model state seen by Django
and lead to destructive changes. New generated projects now pin active
profiles in `primarykit-origin.json`; the offline doctor refuses profile
drift even if every dependent module happens to be installed.

When a mode-owning module is installed later, the installer pins the current
setting. Clients created earlier without `schema_modes` continue to work,
but must review their effective profile before opting into a source upgrade.

**Versioned migration history is not shipped yet.** Do not copy an upstream
tenant migration to a standalone client. The remaining #88 milestone must:
- Make separate reviewed and immutable migration graphs for both schema profiles,
  including dependent migration edges and the custom user model.
- Introduce an explicit opt-in migration adoption plan for existing client graphs.
  Never rewrite applied client migrations or use `--fake` without checking live schema.
- Exercise PostgreSQL stateful migration tests including retained data,
  concurrent DDL and `makemigrations --check --dry-run`.
- Lint emitted SQL using Squawk and review long table locks.

This guard is a compatibility prerequisite, not an automatic migration upgrade.
