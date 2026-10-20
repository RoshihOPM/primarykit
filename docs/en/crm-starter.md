# CRM starter — independent modules

Generate a standalone Django backend:

```bash
uv run python scripts/new_project.py ../my-crm --name my-crm --preset crm
cd ../my-crm
uv run python manage.py makemigrations users audit storage organizations tasks kanban leads contacts deals crm_pipeline
uv run python manage.py migrate
```

The CRM preset composes standalone `kanban`, `leads`, `contacts` and `deals`\nmodules and an explicit `crm_pipeline` **adapter**. The four standalone modules\nhave no direct business-model foreign keys or imports between each other; only\nthe opt-in adapter holds the mapping between Deal and Card. Any one module can also be selected alone via `--apps` and
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
- `/api/v1/leads/` — independent lead CRUD without DELETE
- `POST /api/v1/leads/{id}/transition/` —
  `{"status":"qualified","expected_version":0}`
- `/api/v1/contacts/` — standalone private contact directory without DELETE
- `/api/v1/crm/pipeline/links/` — bind Deal to Card; `POST` uses `deal_id`, `card_id`\n- `/api/v1/deals/` — private deals with amount in integer minor units and
  three-letter ISO-style currency codes
- `POST /api/v1/deals/{id}/transition/` —
  `{"stage":"negotiation","expected_version":0}`

Leads, Deals and Contacts PATCH requests require `expected_version`; stale
updates return 409. Read/write permission is always owner-only and scoped on
every endpoint. Versions prevent lost updates between supported service calls.

An optional `assigned_to` identifies the responsible active user but **never grants access**.\nOnly the owner (self) may be assigned in standalone mode. When Organizations is\nselected, the owner can also assign an active member of an active organization\nshared with them; access remains owner-only. A revoked membership prevents future\nassignments. Lead creation, updates and transitions record optional audit events.\nFilters operate strictly inside the authenticated owner's queryset and are bounded.\n\n
## Deal/Kanban transactional projection\n\nCreate an owner-private Kanban board containing exactly one column with each\ncase-insensitive Deal stage name: `open`, `negotiation`, `won`, `lost`. Create a\nDeal and a Card in the matching initial column, then bind them using\n`POST /api/v1/crm/pipeline/links/`. Every subsequent authoritative Deal\n`transition` synchronously moves the mapped Card in the **same database\ntransaction**. A missing or ambiguous stage column rolls back the Deal change.\nDirect card moves across stages are rejected while bound. Binding is one-to-one\nand restricted to the current owner; stale versions still return 409.\n\nThe adapter is enabled explicitly by `--apps crm_pipeline` (also included by the\n`crm` preset). Unselected base modules remain independent. Clients must review\nthis synchronous projection's lock ordering and transaction duration at scale;\nno asynchronous projection or external event processing occurs.\n\n## Deliberate limitations

- No associations among standalone Lead, Deal, Contact and Card; only the optional\n  CRM Pipeline adapter maps a Deal to a Card. Other business associations belong\n  to the generated client.
- No organization-wide permissions, assignees, custom fields, drag-and-drop
  frontend, background automation, revenue accounting or pipeline reports.
- No hard delete endpoints: personal-data deletion/export and retention policies
  must be implemented per deployed client's legal obligations.
- Kanban's same-board integrity is enforced by the supplied API/service, not
  by a cross-table SQL CHECK constraint; bypassing services is unsupported.
- Values in Deals are not payment settlement, invoices, nor bank transactions.
- Copy-based modules ship no reusable migrations. Generate and commit your own.
