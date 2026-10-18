# Listings — independent classified-ad backend (v1)

`apps/listings` is an **optional** seller-owned classifieds module for
marketplaces: vehicles, property, jobs, equipment or services. It is NOT a
product Catalog. No SKU/inventory stock, checkout, payment gateway, credit
balance, vehicle VIN rules, contacts or SEO frontend is included.

The existing `apps/catalog` stores owner/tenant product SKU and typed
attributes; **do not reuse CatalogItem as a seller's ad**. The customer's
`apps/vehicles` can provide make/model/year/VIN reference data and validate
`Listing.attributes` under client-owned rules.

## Installation

```bash
uv run python scripts/new_project.py ../classifieds-api --name classifieds-api --apps listings
cd ../classifieds-api
uv run python manage.py makemigrations users listings
uv run python manage.py migrate
```

Categories are managed by **trusted staff** through Django Admin or client
fixtures. No public category-creation endpoint exists. The Catalog module is
not required.

## HTTP endpoints

- `GET /api/v1/listings/`: publicly published, paginated ads; filters
  `category`, `q`, `location`, `min_price`, `max_price`.
- `GET /api/v1/listings/categories/`: public active taxonomy.
- `GET /api/v1/listings/{id}/`: published ads; seller can also view own drafts.
- `GET /api/v1/listings/mine/`: seller's own ads, all statuses.
- `POST /api/v1/listings/`: verified authenticated seller creates a draft.
- `PATCH /api/v1/listings/{id}/`: seller edits only draft/rejected, with
  `expected_version` supplied; version mismatch returns 409.
- `POST /api/v1/listings/{id}/submit/`: draft/rejected -> pending.
- `GET /api/v1/listings/pending/`: users with `listings.moderate_listing` only.
- `POST /api/v1/listings/{id}/moderate/`: permission-bound moderator sends
  `{"expected_version": 1, "decision": "approve"}` or `reject`.
- `POST /api/v1/listings/{id}/archive/`: seller archives their draft/rejected
  or published ad.
- `POST /api/v1/listings/{id}/mark-sold/`: seller marks published ad sold.

The API never exposes draft or pending ads to unrelated users, including
Django superusers (except a separate moderator list for authorized staff).
Moderators cannot modify sellers' listing fields or approve their own listing.
The status lifecycle is checked in pure domain rules and mutated under a
row lock and conditional version update in a PostgreSQL transaction.
The default list uses bounded pagination; numeric price is stored in integer
**minor units** with ISO-style three-letter uppercase currency code.

`Listing.attributes` is an intentionally bounded, shallow JSON object (up
to 24 keys, 8 KiB). These attributes are **not trusted vehicle specifications**;
client-owned validators must enforce per-category schemas and allowed values.

## v1 limits and next modules

- **Photos:** private Storage is not a public CDN. Do not simply expose
  signed/private file URLs to anonymous listing browsers. A public media
  publishing policy, ownership check, quotas, moderation and cleanup need
  a separate reviewed adapter.
- **Location:** `location_label` is descriptive only. No geocoding/distance search.
- **Favorites and saved searches:** optional `favorites` adds owner-private
  bookmarks and bounded filters, but no automatic notifications. See [Favorites](favorites.md).
- **Promotion credits, reviews, dealer accounts and seller messaging:**
  separate optional modules and permission contracts. Private Chat is
  not automatically linked to Listing.
- **Organizations:** no implicit dealer organization ownership: listings are
  personal until the client deliberately designs and migrates tenant semantics.
- **Moderation:** sample manual approve/reject only. No automated spam/fraud
  prevention, verification of VIN, safety checks or legal compliance.
- **Retention:** archived/sold rows remain and follow client-owned privacy
  rules; this module performs no automatic deletion.

For public production systems also apply shared abuse throttling, spam
defences, abuse reporting, public image-safety checks, audit monitoring and
an API load test. Run PostgreSQL race tests; SQLite locks do not simulate them.
