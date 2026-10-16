# Catalog: organization-scoped product catalog

**Required dependency: Organizations.** Every `Category` and `CatalogItem`
belongs to an `Organization` through a non-null FK. AttributeDefinition belongs to
a category, inheriting the company boundary. Products and categories cannot be
created without an organization. The client's request cannot set or change it.

## API and access

All routes require an active membership, even for Django superusers:

```
/api/v1/organizations/{org_id}/catalog/categories/
/api/v1/organizations/{org_id}/catalog/attributes/
/api/v1/organizations/{org_id}/catalog/items/
```

An authenticated, active member can read active items, categories and definitions
of their company. Owners, admins and managers can also create/update items,
categories and definitions; they can view inactive items and categories to
reactivate them. No hard delete endpoint is provided.

Category `slug` and case-insensitive `CatalogItem.sku` are unique **per
organization**, not globally. Identical codes may exist in two companies.
Category and item organization FKs are checked on every API input;
foreign UUIDs cannot retrieve or mutate another company's objects.

CatalogItem has a separate organization FK for fast indexed filtering; its
category must belong to the same organization, checked by the serializer and
model save. Direct SQL and `QuerySet.update()` can bypass this application
check: restricted DB writers or additional DB triggers/RLS are appropriate
for higher-assurance multi-tenant deployments.

Type-safe category attributes (text, integer, decimal, boolean) stay in JSON;
frequently filtered business fields should become explicitly indexed columns.
Changing definition types for existing products requires a data migration and
validation of all existing items. Catalog intentionally excludes prices, balance,
lots, tax and accounting.

## Breaking upgrade: migrate old standalone catalogs carefully

Old global endpoints `/api/v1/catalog/*` are deliberately removed. Old
global Catalog data has no known tenant, so PrimaryKit **never assigns it to a
company automatically**.

For an existing installation: first create the real organizations, plan a
verified mapping for each category/item, then add nullable organization FKs in
a client-specific expand migration, backfill after review, validate foreign
category references and SKU duplicates, then set `NOT NULL` and enable the
tenant route/queryset. Preserve all historical client migrations.
Do not copy the new models and blindly invoke `makemigrations` on existing
populated databases: that would request a one-off default or fail.

Fresh generated projects create/commit `users organizations catalog`
migrations directly.

## Standalone и tenant режимы (ADR 0005)

`CATALOG_MODE="standalone"`: самодостаточные Category, AttributeDefinition, CatalogItem. Категории и позиции принадлежат конкретному пользователю; owner назначается только сервером, данные чужих пользователей (включая от глобального Django superuser) скрыты. URL: `/api/v1/catalog/categories/`, `attributes/`, `items/`. Organizations **не нужен**.

`CATALOG_MODE="tenant"`: исходные модели с обязательным Organization FK и корпоративными правами, URL `/api/v1/organizations/{org_id}/catalog/`. Режим фиксируется **перед первой миграцией**, простой сменой настройки на существующей базе переключать нельзя. См. [ADR 0005](adr/0005-standalone-catalog-inventory.md).
