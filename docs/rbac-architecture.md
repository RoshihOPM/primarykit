# PrimaryKit RBAC — v0.1

## Design

Reuse Django **Group** as Role, Django **Permission** as permission and `User.groups` as assignments. No duplicate Role/Permission tables or extra migrations. Groups contain Django model permissions; project-specific apps can add custom model permissions via `Meta.permissions`. Role IDs are Django Group integer IDs; user IDs remain UUID.

### Authority model

- **Role management:** active superusers only. Ordinary staff never receives RBAC administration powers by assigning an arbitrary group. For a project-specific delegated role manager, implement a separately reviewed endpoint.
- **Assignable permission catalog:** `RBAC_ASSIGNABLE_PERMISSIONS` is an exact list of `"app_label.codename"` codes. Default empty, so nothing is assignable until a client deliberately opts in. This avoids universal escalation through `auth.change_group` or `users.change_user`.
- **Roles:** create/list/detail/PATCH/delete. Assigned roles cannot be deleted using this API. Role permission changes take effect in the database; in-process Django User instances can cache permissions until reloaded.
- **User role assignments:** superuser PUT replaces role IDs atomically inside a transaction with the user row locked. GET returns current role IDs/names. No public self-assignment.
- **Admin API:** existing users admin remains superuser only. RBAC grants do not implicitly elevate it.

## HTTP endpoints

| Method | Path | Access |
| --- | --- | --- |
| GET/POST | `/api/v1/admin/rbac/roles/` | Active superuser |
| GET/PATCH/DELETE | `/api/v1/admin/rbac/roles/{id}/` | Active superuser |
| GET | `/api/v1/admin/rbac/permissions/` | Active superuser; assignable allowlist only |
| GET/PUT | `/api/v1/admin/rbac/users/{uuid}/roles/` | Active superuser |

Role create/PATCH accepts `name`, `permission_codes` as an array of allowlisted permission strings; GET returns `permissions` as code strings. PUT user roles accepts `{"role_ids":[1,2]}`.

## Reuse in business apps

For routes where *every* access must have permissions, use `HasRequiredPermissions` and `required_permissions = {"GET": ["catalog.view_catalogitem"], ...}`. Missing method configuration fails closed.

For owner-specific lists and details use **both** `OwnerScopedQuerysetMixin` and `IsOwnerOrGlobalPermission`; configure `owner_lookup` for filtering and `owner_attribute` for object checks. Global scope permissions are explicitly configured **per HTTP method**. Read-all access must not automatically grant patch-all. Never trust a UUID as proof of ownership, and never set owner from untrusted input on create.

Django's default permission backend does NOT implement persistent per-object `has_perm(code, obj)`. The provided helper is ownership-based. True arbitrary object ACL / tenant-scoped role grants need a separate explicit design (e.g. django-guardian or a membership table), not a hidden claim of support.

## Safety / trade-offs

- Default Group model is sufficiently capable for global roles and avoids unnecessary schema/migration complexity.
- When the business needs organization-scoped permissions, membership with role/scope must be modeled separately: globally assigning Group to a user would cross tenant boundaries.
- Role deletion and updates need audit events and human review in production; event log is planned for an Audit module.
- Permission changes take effect at the next database-backed request; access JWTs are not used to carry role grants, preventing stale claims from authorizing API actions.
- No distributed permission cache; Django may cache permissions per in-memory User instance during one request. Refresh objects if changing permissions inside long-running tasks.
- Security test matrix covers privilege escalation, IDOR, role replacement, default-deny and cross-method write access.

## Schema/migrations

RBAC reuses Django `auth_group`, `auth_permission`, `auth_group_permissions` and `users_user_groups`. Client project initial `users` migration must be committed. No rbac app migrations are needed.
