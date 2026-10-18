# Kanban foundation (opt-in)

Select `--apps kanban`. This is a backend model/service building block, **not**
a ready-made CRM, workflow engine, REST API or drag-and-drop frontend.

- `Board` is owned by a user; `Column` belongs to one board.
- `Card` belongs to one board and one column; `CardMove` records moves.
- `move_card(actor, card_id, target_column_id, expected_version)` enforces
  board ownership, same-board destinations, optimistic version checks and
  transactional locking. The `position` argument provides atomic dense card reordering; `edit_card` provides versioned title/description updates.
- Run `makemigrations kanban` then `migrate` in the generated client and
  commit **client-owned** migrations.
- Client apps must enforce access for any custom read/write endpoints and
  avoid unscoped ORM writes; service invariants are not database constraints.
- CRM Leads should own their own lead statuses and explicitly synchronize
  relevant transitions within the same transaction.
- Multi-user board ACL, tenant scoping, drag-and-drop frontend, invitations,
  event retention, and public routes are intentionally out of scope for v0.
