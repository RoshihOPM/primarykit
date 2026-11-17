# PostgreSQL generated client CI

The catalog runs fast SQLite unit tests and Docker PostgreSQL integration tests.
An independent `generated-clients` matrix generates minimal, individual, CRM,
marketplace, commerce and all-module projects and executes real PostgreSQL 17
migrations and pytest. Every project runs `makemigrations --check --dry-run`
after the initial schema generation. This catches divergent model states, but
not production DDL lock hazards.

Generated projects do not inherit this catalog workflow. The generator writes a
small dedicated client workflow from `scripts/templates/client-ci.yaml` (locked
sync, doctor, Ruff, then `makemigrations --check --dry-run`, `manage.py check`
and pytest on a PostgreSQL 17 service). It never generates migrations: a client
without committed migrations fails with a "commit your migrations" message.
After the PostgreSQL integration tests, the catalog uses a pinned Squawk CLI
to lint SQL from **Git-tracked, non-initial, versioned source migrations only**.
Transient `makemigrations` output (including multi-part `0002_initial`
histories for new empty schemas) is not an upgrade and must not be scanned as
one. The pinned CLI is verified even when no upgrades exist. Empty
`sqlmigrate` output and renderer/linter errors fail closed. Tests cover
tracked-file discovery, invocation and failure propagation.

This static lint cannot review `RunPython` data changes, retroactively
validate clients' own migrations or replace a production migration plan.
Full adoption and compatibility of versioned histories remain tracked under #88.
