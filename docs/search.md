# Portable PostgreSQL Search

`apps/search` is an optional, stateless source module: no new table, migrations, global API, Elasticsearch or runtime dependency on PrimaryKit.

## Application contract

Call `search_queryset(authorized_queryset, scope_filters={"organization_id": verified_org_id}, text=term, fields=("name", "description"), limit=25)`. The **authorized_queryset** must already enforce membership/permissions. `scope_filters` must be nonempty **and derived from server-verified context**, not from HTTP request parameters. Both filters are applied together. This helper cannot prove that an arbitrary user-supplied organization ID is authorized: the endpoint and service must validate that independently.

Only local CharField/TextField columns are allowed, not relationship traversals; no client-supplied ORM lookups, field lists, unbounded offsets or sort expression. Query terms are capped at 200 characters, fields at eight, results at 100. Queries use PostgreSQL `websearch_to_tsquery` with `simple` config. There is no SQLite fallback, except for fast input-validation tests; PostgreSQL integration tests are mandatory.

## Operations and trade-offs

The current implementation computes a vector at query time. It is suitable for **modest owner/tenant partitions**, not global millions-of-row catalogues. Measure `EXPLAIN (ANALYZE, BUFFERS)` on staging with realistic cardinality. For growing datasets, add **client-owned** expression or generated `tsvector` + GIN indexes matching the actual query and FTS configuration. Always index the owner/organization scoping keys too.

No generic search route is registered. Clients add their own authorization, rate limiting, response schema and query budgets. Never use search as an access-control check.
