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

- **Photos (opt-in):** private, moderated image adapter in `apps/listings`;
  see the security and operations contract below. No Storage dependency.
- **Location:** `location_label` is descriptive only. No geocoding/distance search.
- **Favorites, promotion credits, reviews, dealer accounts and seller messaging:**
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

## Optional moderated listing photos (Issue #64)

The optional media adapter is disabled by default. It requires **no** `apps/storage`.
Generated projects without photos work without Pillow. Enable photos only after
installing the image decoder into the **generated client's own** lockfile:

```bash
uv add 'Pillow>=11,<13'
# In client-owned trusted Django settings:
# LISTINGS_MEDIA_ENABLED = True
uv run python manage.py makemigrations users listings
uv run python manage.py migrate
```

The separate `STORAGES["listings_private"]` alias defaults to a directory
`BASE_DIR/privatefiles/listing-media/`, **outside** MEDIA_ROOT/static paths.
It never uses `apps/storage` or exposes a signed object URL. In production
configure this alias to a durable **private** S3/bucket/filesystem backend;
never grant public-read, mount the folder behind Nginx or put it under a
public CDN origin. Ensure this directory has durable volumes, encryption
and its own backup/retention policy.

**Endpoints** (all under `/api/v1/listings/`):

- `POST {listing_id}/media/`: verified owner uploads multipart
  `file` and `expected_version`, only draft/rejected listings.
- `GET {listing_id}/media/`: visible photos. Public gets only approved
  images of published ads with active, verified sellers; owner can view
  private/pending assets; trusted listing moderators inspect pending ads.
- `GET {listing_id}/media/{image_id}/`: stable relative media URL.
  Authenticated owner/moderator previews or anonymous publicly approved
  images are streamed as normalized JPEG; no raw private URL/redirect.
- `POST {listing_id}/media/{image_id}/moderate/`:
  authorized moderator (not the seller) explicitly approves or rejects
  pending images while the listing is pending; requires `expected_version`.
- `DELETE {listing_id}/media/{image_id}/`: verified seller with
  `expected_version`, except while listing is awaiting moderation.

A listing cannot be approved while any photo is unreviewed. All image state
changes lock the parent listing row and increment `Listing.version`, so
concurrent content edits, upload, review and publish cannot silently race.
No global superuser override for another seller's assets. All client-IDs
are resolved under listing ownership, and image UUIDs are not permission.

Accepted uploaded bytes: JPEG, PNG, WebP only, with a matching real decoded
format; **5 MiB input/output cap**, **16 million decoded pixels**, max
**8 images per listing**. Pillow decodes, normalizes EXIF orientation,
strips embedded metadata and re-encodes a max-2048px JPEG. Raw originals,
SVG, GIF, scripts, untrusted filenames and caller-supplied object keys are
never published.

**Private-to-public policy and CDN:** Binaries always remain private.
The public adapter grants image bytes only after **both** image moderation
and listing publication. `GET` checks listing status, active/verified seller
and image approval at request time, then streams the sanitized private object.
`Cache-Control: no-store, max-age=0` is set on every response; there is
**no public CDN caching by default**. This gives an immediate 404 on
unpublish, mark-sold, seller deactivation and deletion without relying on
a best-effort asynchronous CDN purge. For a high-traffic CDN deployment,
introduce **versioned public derivatives and reliable purge/invalidation**
with short bounded TTL only after a separate takedown/security review.
Streaming via Django consumes API worker capacity; this secure default
is intended for modest loads or an identity-aware edge offload.

Orphan blobs can remain after DB rollback, storage write failure or interrupted
cleanup: storage operations are not transactionally atomic with PostgreSQL.
Schedule `python manage.py purge_listing_media --days 7 --limit 500` for
old closed/rejected listings and old unreferenced blobs. It intentionally
never deletes recently uploaded content. Monitor storage failures and job
lag; for very large buckets, use bucket lifecycle/partitioned prefixes
instead of scanning huge namespaces.

Production additionally needs edge request body caps (Nginx
`client_max_body_size`), shared authenticated upload throttling, malware/
fraud moderation and privacy/backup review. Per-process DRF throttling
alone is insufficient for abusive traffic.
