# PostgreSQL generated client CI

The catalog runs fast SQLite unit tests and Docker PostgreSQL integration tests.
An independent `generated-clients` matrix generates minimal, individual, CRM,
marketplace, commerce and all-module projects and executes real PostgreSQL 17
migrations and pytest. Every project runs `makemigrations --check --dry-run`
after the initial schema generation. This catches divergent model states, but
not production DDL lock hazards.

The catalog-only CI runner and matrix job are stripped from generated projects.
Committed migration histories and automated Squawk SQL linting remain separate
follow-ups under #88: initial `makemigrations` is not equivalent to an upgrade.
