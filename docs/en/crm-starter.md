# CRM starter (API building blocks)

Generate a standalone Django backend:

```bash
uv run python scripts/new_project.py ../my-crm --name my-crm --preset crm
cd ../my-crm
uv run python manage.py makemigrations users audit storage organizations tasks kanban leads
uv run python manage.py migrate
```

The CRM preset includes Kanban and Leads plus existing infrastructure. It is not a
Bitrix clone or a complete CRM. The starter does not automatically synchronize
Kanban cards and Leads, create UI screens, provide multi-user team access, or
manage contacts/deals. Those business rules remain client-owned.

## Endpoints

- `/api/v1/kanban/boards/` — user-owned boards
- `/api/v1/kanban/columns/` — columns inside accessible boards
- `/api/v1/kanban/cards/` — cards inside accessible boards
- `POST /api/v1/kanban/cards/{id}/move/` — body:
  `{"target_column_id":"<uuid>","expected_version":0}`
- `/api/v1/leads/` — owner-scoped lead CRUD (no DELETE)
- `POST /api/v1/leads/{id}/transition/` — body:
  `{"status":"qualified","expected_version":0}`

JWT authentication is required. Non-owners cannot access data. Lead status changes
are serialized under a row lock and detect stale versions (409). Basic card moves
also use a row lock and version; non-versioned card edits are disabled. Concurrent
PostgreSQL verification and code review are required before production adoption.

## Known limitations

- Owner-only, not organization-wide permissions. Installing `organizations`
  does **not** automatically make Kanban/Leads tenant-aware.
- Contacts are embedded as lead fields in this initial starter. PII retention,
  purpose limitation, export and deletion must be designed per client.
- Kanban placement is not a source of truth for lead status, and cannot be
  automatically mapped to domain stages.
- No ordered drag-and-drop reorder, per-column WIP limits, leads assignment,
  deals, custom fields, automations, or UI.
- Copy-based modules ship without migrations; generate and commit the client
  schema before deployment.
