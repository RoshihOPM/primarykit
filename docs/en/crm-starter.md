# CRM starter — independent modules

Generate a standalone Django backend:

```bash
uv run python scripts/new_project.py ../my-crm --name my-crm --preset crm
cd ../my-crm
uv run python manage.py makemigrations users audit storage organizations tasks kanban leads contacts deals
uv run python manage.py migrate
```

The CRM preset **composes** the standalone `kanban`, `leads`, `contacts` and
`deals` modules; it does not introduce database foreign keys or business imports
between them. Any one module can also be selected alone via `--apps` and
generated with only its required `users` dependency. Each module uses an
owner-only API (JWT required). Adding `organizations` or `rbac` does not
automatically provide tenant or team ACLs.

## Endpoints

- `/api/v1/kanban/boards/` — private boards
- `/api/v1/kanban/columns/` — columns within private boards
- `/api/v1/kanban/cards/` — standalone cards
- `POST /api/v1/kanban/cards/{id}/move/` —
  `{"target_column_id":"<uuid>","expected_version":0,"position":0}`
- `PATCH /api/v1/kanban/cards/{id}/` —
  `{"expected_version":0,"title":"Revised"}`
- `/api/v1/leads/` — independent lead CRUD without DELETE; list filters: `?status=new&source=website`
- `POST /api/v1/leads/{id}/transition/` —
  `{"status":"qualified","expected_version":0}`
- `/api/v1/contacts/` — standalone private contact directory without DELETE; `?company=Acme`
- `/api/v1/deals/` — private deals with amount in integer minor units and
  three-letter ISO-style currency codes
- `POST /api/v1/deals/{id}/transition/` —
  `{"stage":"negotiation","expected_version":0}`

Leads, Deals and Contacts PATCH requests require `expected_version`; stale
updates return 409. Read/write permission is always owner-only and scoped on
every endpoint. Versions prevent lost updates between supported service calls.

An optional `assigned_to` identifies the responsible active user but **never grants access**.\nOnly the owner (self) may be assigned in standalone mode. When Organizations is\nselected, the owner can also assign an active member of an active organization\nshared with them; access remains owner-only. A revoked membership prevents future\nassignments. Lead creation, updates and transitions record optional audit events.\nFilters operate strictly inside the authenticated owner's queryset and are bounded.\n\n## Deliberate limitations

- No association between Lead, Deal, Contact or Kanban Card. A generated client
  must explicitly design its own domain associations; core source modules remain
  independent.
- No organization-wide permissions, shared assignee access, custom fields, drag-and-drop
  frontend, background automation, revenue accounting or pipeline reports.
- No hard delete endpoints: personal-data deletion/export and retention policies
  must be implemented per deployed client's legal obligations.
- Kanban's same-board integrity is enforced by the supplied API/service, not
  by a cross-table SQL CHECK constraint; bypassing services is unsupported.
- Values in Deals are not payment settlement, invoices, nor bank transactions.
- Copy-based modules ship no reusable migrations. Generate and commit your own.
