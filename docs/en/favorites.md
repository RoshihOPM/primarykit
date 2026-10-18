# Favorites and saved searches — Issue #65

`apps/favorites` is a portable, opt-in module selected with `--apps favorites`.
It requires `listings` (and transitively `users`) but not Catalog, Tasks,
Outbox, Redis or WebSockets.

## Generate a standalone client

```bash
uv run python scripts/new_project.py ../classifieds-api --name classifieds-api --apps favorites
cd ../classifieds-api
uv run python manage.py makemigrations users listings favorites
uv run python manage.py migrate
```

Generate, review and commit migrations in the **client repository**.
Do not replace an existing client's migration history.

## Authenticated API

Requests require an active, email-verified account. Staff/superuser flags
do not grant cross-user visibility.

- `GET /api/v1/favorites/`: paginated owner-only visible bookmarks including
  published listing fields.
- `POST /api/v1/favorites/` with `{"listing_id":"UUID"}`: add a public listing
  from an active verified seller (201 new, 200 on duplicate).
- `GET /api/v1/favorites/{id}/`: one visible personal bookmark.
- `DELETE /api/v1/favorites/{id}/`: remove your bookmark even after unpublishing.
- `GET/POST /api/v1/saved-searches/`: list/create saved searches.
- `GET/PATCH/DELETE /api/v1/saved-searches/{id}/`: own saved searches only.

A saved search is `{"name":"Cars","filters":{"category":"cars","min_price":100}}`.
Only Listings v1 public filter keys are accepted: `category` (slug, 1–80),
`q` (1–80), `location` (1–120), `min_price` and `max_price`
(integer minor units 0–10^15). Nested/unknown parameters, booleans as prices,
blank values and reversed price ranges are rejected. Up to **20 searches**
are saved per user.

## Security, consistency and rollout

Unique (owner, listing) prevents duplicate bookmarks under concurrent writes.
The saved-search limit is enforced in a PostgreSQL transaction that locks
the user's account row; SQLite does not validate the same concurrency semantics.
Bookmarks are visible only while the listing remains published and the
seller is active and verified. Archived/sold listings become invisible;
the owner may still remove the bookmark by known ID.

DRF applies per-worker 120/min read and 60/min write throttles; in a scaled
environment use shared/edge limits. There are **no automatic notifications**
or subscriptions. A future opt-in saved-search notification feature must be
deduplicated and rely on Tasks/Outbox only when explicitly selected.
