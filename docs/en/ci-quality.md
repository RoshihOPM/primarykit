# PostgreSQL generated client CI

The catalog runs fast SQLite unit tests and Docker PostgreSQL integration tests.
An independent `generated-clients` matrix generates minimal, individual, CRM,
marketplace, commerce and all-module projects and executes real PostgreSQL 17
migrations and pytest. Every project runs `makemigrations --check --dry-run`
after the initial schema generation. This catches divergent model states, but
not production DDL lock hazards.

The catalog-only CI runner and matrix job are stripped from generated projects.
The catalog also invokes a pinned Squawk linter after the PostgreSQL Docker
integration tests. It uses Django's `sqlmigrate` on non-initial migrations, fails on unsafe SQL,
and verifies the pinned CLI version even when no upgrades exist. Empty
`sqlmigrate` output fails closed for manual investigation; CI tests cover
successful invocation and both renderer/linter failures. This static lint
cannot review `RunPython` data changes or replace a production migration plan. Initial new-table DDL is omitted from the upgrade-risk
lane. The generated client does not carry this source-only helper. Full
adoption and compatibility of versioned histories remain tracked under #88.
