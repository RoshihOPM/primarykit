# Shared tenant permission policy (#45)

**Language:** English · [Reference (EN)](../organizations-architecture.md#reusable-tenant-permission-policy-adapter) · [Docs index](README.md)

The optional Organizations module provides `apps.organizations.policy.TenantPolicy`, using the **existing** organization, membership, branch and branch-grant data. No new authoritative role table, global middleware, Django Group mapping or automatic superuser bypass is introduced.

## Lists and details

Resolve with `TenantPolicy.resolve(user=..., organization_id=...)`, where the organization identifier is the authorized, server-validated scope. Apply `policy.scope_queryset(queryset, organization_field="organization")` to **both** list and detail actions; supply `branch_field="branch"` for branch-owned records. Manager/member branch grants are explicit; inactive branches and memberships fail closed.

## Writes and race conditions

Inside `transaction.atomic()`, resolve with `lock=True`, call `policy.require_write()` or `require_roles(...)`, and enforce `require_organization(...)` / `require_branch(...)` for affected objects and foreign keys. The lock order is Organization first, then membership; organization role-change services use the same order. Repeat these checks in service commands, not just serializers.

Missing/cross-tenant/inactive scope produces 404; membership without sufficient role produces 403. Even staff/superusers do not receive automatic tenant access. Raw unscoped ORM operations remain outside the adapter guarantees; custom client APIs must opt in explicitly.

This does **not** make Orders/Sales/Payments tenant-aware automatically. See [module catalog](modules.md).
