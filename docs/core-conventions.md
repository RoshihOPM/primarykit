# Core abstractions and development conventions

## Django project versus reusable code

`config/` is the Django project. `apps/core/` contains minimal cross-cutting utilities only. Feature business logic must stay within its own app. Avoid global `utils.py` as a dumping ground; use domain-specific helpers and constants next to their owner.

## Models

- `UUIDModel`: UUID primary key.
- `TimestampedModel`: `created_at`, `updated_at`.
- `UUIDTimestampedModel`: composition of both, replaces old model without schema changes.
- `SoftDeleteModel`: opt-in `deleted_at`, `objects` filters active rows, `all_objects` includes deleted rows.
- `SoftDeleteUUIDTimestampedModel`: complete convenience combination.

Choose a base per entity; do not enable soft delete for immutable ledger movements, event logs, payment records, or join tables without a domain-specific reason.

### Soft delete contract and sharp edges

`instance.delete()` and `queryset.delete()` issue an UPDATE, return affected count in Django-like form; no cascade, no regular pre/post-delete signals. `hard_delete()` runs ordinary Django deletion including related cascades. `restore()` restores rows; restored data can collide with uniqueness constraints. The unfiltered base manager enables foreign-key relation resolution. Querying active rows is opt-in only for subclasses using this abstract model; raw SQL and unfiltered managers still see deleted data.

**Important:** these helpers do not implement recursive deletion or tombstones across relationships. Do not assume related records are automatically hidden. Consider access scopes in selectors, admin and API carefully. Bulk `update()` and soft-deletion updates do not automatically change `updated_at`; if required, update it explicitly at the operation boundary.

For an email/SKU/name that may be reused after deletion, a partial PostgreSQL unique constraint with `deleted_at IS NULL` may be appropriate; do not blindly combine unconditional `unique=True` with that behavior. SQLite tests do not replace PostgreSQL for this.

## API, services and selectors

- Use Django/DRF CRUD tools directly for simple create/list/detail/update/delete.
- Add `services.py` for business transactions and cross-model invariants; accept explicit IDs and validated data, return domain result, document side effects.
- Add `selectors.py` for complex, reused database reads and prefetch plans; always scope by tenant/object permissions before serializing.
- Put input validation in serializers and business invariants in services/DB constraints. Avoid save-side effects hidden in serializers where retries and transaction boundaries become invisible.
- Use `transaction.atomic` for balance/stock changes and configure explicit idempotency rules for externally repeated calls.
- Migrations are generated and committed in **each client repo**, not the PrimaryKit catalog. Changing copied Apps later requires deliberate migration review.

## Localization

Django's `LocaleMiddleware` is enabled and the initial supported locales are `en`, `ru`, `ko`; `Accept-Language` can select response language. Use `gettext_lazy` for field/help labels and `gettext` for dynamic server-side messages. Mark custom error messages for translation, and run `makemessages` / `compilemessages` in client projects when translations exist.

This only prepares Django's i18n pipeline: **no business content translations, .po translations or translated API catalog exist yet**. Business content should use a separate translation model per entity/group rather than hard-coding one column per locale.

## Verification

- Base abstractions must be exercised with a concrete test model created only during tests.
- PostgreSQL smoke checks and the same pytest suite run against PostgreSQL in CI via `uv run pytest --ds=config.settings.postgres_test`; dedicated multi-writer concurrency and measured query-plan tests should also use PostgreSQL specifically.
- Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`, and `uv run python manage.py check --settings=config.settings.test`.
