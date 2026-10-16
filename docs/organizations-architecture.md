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

## Tenant integration — explicit boundaries

**Catalog and Inventory are now organization-scoped**, with strict nested API
routes and company/branch service validation. Their source code requires this
Organizations app. Existing client installations need controlled tenant
backfill; see [Catalog](catalog-architecture.md) and
[Inventory](inventory-architecture.md) for breaking migration steps.

**Storage files are still owner-scoped, not organization-scoped**. Reuse in a
multi-company product requires an explicit attachment/ACL design; do not expose
file IDs across tenants or assume a user-owned file is company-owned.

Organizations may be selected independently. The generator automatically adds it when a project selects Catalog or Inventory. Do not expose legacy global endpoints in existing projects; use the scoped Catalog/Inventory endpoints only after verified tenant data backfill.

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


### Verification and CI

The source test suite verifies cross-organization object lookup, foreign-branch
assignment rejection, owner handover/last-owner safeguards, replayed or expired
invitations, administrator privilege restrictions and membership revocation.
GitHub Actions also generates and tests an **organizations-only** client project
to ensure this app doesn't accidentally depend on RBAC, Audit, Catalog or Inventory.

### Production readiness

Organizations creation is authenticated but not quota-limited in this baseline;
public deployments should add per-account creation quotas and abuse protection.
The module deliberately does **not** provide an invitation email dispatch or a
public signup-by-invitation workflow. Frontends should show invitations only to
the logged-in, already verified recipient.
