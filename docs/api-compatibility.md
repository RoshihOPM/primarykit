# OpenAPI Contract Comparator

Breaking HTTP interface changes can silently break copied client projects.
The source-only CLI checks two DRF OpenAPI 3.x **JSON** files:

```bash
python scripts/contract_check.py before.json after.json --fail-on-breaking --json
```

Generate baseline/current specs in the client codebase and retain the former
one alongside the branch under review. For DRF Spectacular, the
`manage.py spectacular --format openapi-json` command can produce JSON output;
check the app's configured auth, permissions, migrations and settings.

The comparator reports removed routes/methods, newly required query/path/header
parameters, newly required request bodies, removed 2xx status codes, and manual
review warnings for response content, authentication changes or referenced
parameters. It exits 2 with `--fail-on-breaking` if a detected break occurs.

**Important limits:** references, schema type changes, nested request field
compatibility, authorization, tenant object scope, concurrency, migrations and
business side-effects are not fully checked. A clean comparator result is NOT
proof of backward compatibility. Add positive/negative DRF API regression tests
and explicit IDOR/concurrency checks whenever boundaries change.
