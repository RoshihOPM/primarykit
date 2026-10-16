# Statistics v1 — independent read-only metric aggregation

## Purpose

Copy `apps/statistics/` into a Django project generated from PrimaryKit. It
automatically registers `/api/v1/statistics/` with no settings/URL edits and no
new database tables. By itself it returns an empty personal metric collection;
when optional feature folders are present and provide `statistics.py`, their
metrics are discovered. Statistics never imports another app's ORM models.

## API and authorization

| Route | Authorization | Scope |
| --- | --- | --- |
| `GET /api/v1/statistics/` | Authenticated verified user | Only the actor's own personal data |
| `GET /api/v1/statistics/available/` | Same | Definitions, without running queries |
| `GET /api/v1/organizations/{org_id}/statistics/` | Active company owner/admin membership | Only that company |
| `GET /api/v1/organizations/{org_id}/statistics/available/` | Same | Tenant metric definitions |
| `GET /api/v1/admin/statistics/` | Active authenticated superuser | Aggregate system indicators |
| `GET /api/v1/admin/statistics/available/` | Same | System metric definitions |

The tenant endpoints are registered only if Organizations is installed. A
global superuser cannot bypass company membership. Nonmember or inactive
company -> 404; active member without owner/admin role -> 403. Ordinary
users never receive global registrations or audit counts, including through
the `available/` endpoint.

All metric values are numeric, with stable keys, unit and type. Example:

```json
{
  "scope": "personal",
  "period": {"name": "7d", "start": "2026-10-10", "end": "2026-10-16"},
  "metrics": [
    {"key": "inventory.on_hand", "label": "Quantity on hand", "unit": "units",
     "kind": "snapshot", "value": 17},
    {"key": "inventory.operations", "label": "Stock operations", "unit": "count",
     "kind": "period", "value": 5}
  ]
}
```

`snapshot` metrics are current values regardless of period. `period` metrics
are restricted to `[start 00:00, end + 1 day 00:00)`, in the project timezone.
Pass `?period=today`, `7d` (default), `30d`, or
`?period=custom&start=2026-10-01&end=2026-10-15`. Custom range must be
positive, canonical `YYYY-MM-DD`, and no longer than 366 calendar days.

## How other modules integrate

Each **feature module** optionally owns a `statistics.py` file. It imports
only the core contract, plus its own models:

```python
from apps.statistics.domain import Metric, Provider
from .models import Order

def _my_orders(context):
    return Order.objects.filter(
        owner=context.actor, created_at__gte=context.since,
        created_at__lt=context.until,
    ).count()

PROVIDER = Provider(
    code="orders",
    metrics=(
        Metric("created", "Created orders", "count", "period",
               ("personal",), _my_orders),
    ),
)
```

No `statistics.py` means the module contributes no metrics, not an error.
Stats finds providers only among `INSTALLED_APPS`, and only metrics matching
the already-authorized scope. The `context` includes `actor`,
`organization` (tenant only), `since`, `until`, `period`, and `scope`.

**Provider security is critical:** every query must filter by the appropriate
owner or organization. Metadata/availability must not expose sensitive
identifiers. Do not register costly joins, arbitrary client-supplied ORM
expressions or secret data. If a module supports both standalone and tenant
schema modes, register metrics only for the current pinned mode. Avoid database
queries at import time. Statistics validates numeric return types but cannot
prove the correctness of a third-party provider's query filters: review
providers before installing code.

## Implemented providers

- **Users** (system only): total/active users, period registrations.
- **Audit** (system only): period event count.
- **Catalog** (personal in standalone, company in tenant): items, active items,
  categories, period created items.
- **Inventory** (personal or company depending on schema mode): warehouse count,
  current on-hand/reserved quantity, period stock-operation count.
- **Storage**: active personal/tenant file counts, byte totals, period uploads;
  excludes soft-deleted files and exposes no S3 keys.
- **Organizations** (tenant owner/admin only): active memberships and branches.

## Copy-first workflow

```bash
uv run python scripts/new_project.py ../stats-api --name stats-api --apps statistics
# Or from a trusted checkout, inside a generated baseline:
python manage.py install_kit_module statistics --source ../primarykit
# Or simply copy the folder to apps/statistics/ and restart Django.
```

Statistics adds no migrations. Existing providers work if copied later,
without modifying Statistics. Django project baseline and Python package
requirements still apply. Analytics is calculated on request via ORM; no
Celery, Redis or materialized aggregates yet. Add caching/async aggregation
only with measured query cost and explicit invalidation rules.

## Tests

`apps/statistics/tests/` exercises provider discovery, personal isolation,
company owner/admin rules, superuser-only system metrics, date validation
and schemas when optional apps are missing. CI generates a statistics-only
project and a statistics+standalone Inventory project, runs PostgreSQL
integration tests, and exercises S3/SeaweedFS for Storage.
