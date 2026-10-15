# Organizations & Memberships v0.1

## Design and trust boundary

Organizations is an optional app implementing **organization-scoped** membership and
branch access. It does not use Django Group as an organization role because Groups
are global to each Django user; that could accidentally grant rights across companies.

Models: `Organization`, `Membership` (one row per organization/user, roles
owner/admin/manager/member), `Branch`, `BranchAccess` (per-member assignment),
`Invitation` (existing verified account, pending/accepted/revoked, seven-day expiry).

The creating user becomes the **first owner atomically**. Each company may have
multiple owners. The last active owner cannot be demoted or deactivated.
An owner may assign additional owners via PATCH of an existing membership, but
invitations can only specify admin/manager/member roles.

Owners and admins have access to all active branches. Managers and members see only
branches assigned explicitly. Admins may invite/modify managers and members but
cannot promote anyone to admin/owner or remove those privileged members.
Changing these roles requires an owner. A Django superuser has **no automatic
cross-organization access** through this app.

### Access policy

- Organization list shows only organizations where the caller is an active member.
- For list and detail, membership must match the organization UUID. Unauthorized
  organization/branch details return 404 rather than an existence oracle.
- Member and invitation management endpoints require owner or admin role.
- Branch assignments are checked against the selected organization. It is not
  possible to grant a foreign branch via the API.
- All role, invitation and branch-grant mutations lock the Organization row
  and run atomically with Audit when installed.
- Invitations do not confer access until the invited **authenticated** user
  explicitly accepts. They appear via GET `/api/v1/invitations/mine/`. This version
  intentionally does not send email, so acceptance happens inside a client UI.

### Routes

| Method | Route | Access |
| --- | --- | --- |
| GET/POST | /api/v1/organizations/ | Authenticated; list mine/create own |
| GET/PATCH | /api/v1/organizations/{uuid}/ | Member GET, owner/admin PATCH |
| GET/POST | /api/v1/organizations/{uuid}/branches/ | Scoped GET; owner/admin create |
| GET/PATCH | /api/v1/organizations/{uuid}/branches/{uuid}/ | Scoped GET, owner/admin PATCH |
| GET | /api/v1/organizations/{uuid}/members/ | Owner/admin |
| PATCH/DELETE | /api/v1/organizations/{uuid}/members/{uuid}/ | Owner/admin (owner safeguards) |
| GET/PUT | /api/v1/organizations/{uuid}/members/{uuid}/branches/ | Owner/admin |
| GET/POST | /api/v1/organizations/{uuid}/invitations/ | Owner/admin |
| DELETE | /api/v1/organizations/{uuid}/invitations/{uuid}/ | Owner/admin (role restrictions apply) |
| GET | /api/v1/invitations/mine/ | Authenticated invitee |
| POST | /api/v1/invitations/{uuid}/accept/ | Exact invited account only |

API serializers never expose a writeable `organization`, `owner`, `created_by`
or tenant-ID field on the mutations that derive these values from the path or
logged-in identity.

## Tenant integration — important non-goal

**This release does not yet enable multi-tenancy for Catalog or Inventory.**
Those apps still have global rows and global superuser-only writes. Simply adding
Organizations must **not** be described as isolating catalog items, warehouses,
inventory operations or uploaded files. Real multi-tenancy requires a separate
schema migration introducing tenant FKs, required organization-scoped querysets,
cross-tenant FK validation, transaction-bound role checks and backfill from
legacy unscoped rows, plus tests that prove no cross-company reads or writes.

For client projects choose `organizations` by itself only if the business
data is separately scoped. Until Catalog/Inventory are wired, do not expose
global catalog/inventory endpoints to ordinary tenant users.

## Security, operations and migration guidance

- Keep foreign keys under explicit organization checks, not just UUID concealment.
- BranchAccess rows are created only by services, which validate both FK tenant
  identities. Cross-org raw ORM writes remain possible for privileged app code.
- Organization removal is out of scope; use a reviewed retention/offboarding flow.
- Invitations are to an existing verified account; new-user onboarding by email,
  retry/expiry cleanups and anti-enumeration controls require a follow-up design.
- Organization creation should receive abuse limits/quotas before broad public
  signup. Applications can additionally require staff or paid onboarding.
- Schema changes and generated migrations belong to each newly generated client
  repository. PostgreSQL is required for production and concurrency review.
