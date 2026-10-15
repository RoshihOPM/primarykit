# Users API v0.1: architecture and threat model

## Goals and non-goals

PrimaryKit users provides email-based identity, public-registration toggle, JWT login/refresh/logout, own profile, password change and superuser-only user administration. Email verification and password reset are in the separate [email workflow module](email-notifications.md). MFA, invitations, social login and tenant-scoped RBAC remain out of scope. Do not deploy public registration without abuse controls.

## Data

- `users.User` inherits Django `AbstractUser`, uses UUID primary key and canonical casefolded email.
- Unverified registrations are prevented from using JWT/session APIs until email ownership has been confirmed. Superusers created via `createsuperuser` are explicitly marked verified.
- PostgreSQL/SQLite case-insensitive uniqueness constraint: `UniqueConstraint(Lower("email"))`. Keep it when creating a new project. Switching an existing project requires an explicit uniqueness audit and migration.
- `is_staff`, `is_superuser`, groups and permissions use Django auth; no public API writes these fields.
- `password` is hashed by Django; no custom password crypto.
- `rest_framework_simplejwt.token_blacklist` uses package-managed migrations to revoke refresh tokens. Access tokens are short lived and are not revoked immediately by logout; changing password revokes old tokens via `CHECK_REVOKE_TOKEN`.

## API

| Method | URL | Authorization |
| --- | --- | --- |
| POST | /api/v1/auth/register/ | Public only when `ALLOW_PUBLIC_REGISTRATION=true` |
| POST | /api/v1/auth/login/ | Anonymous credentials; rate limited |
| POST | /api/v1/auth/refresh/ | Valid refresh token |
| POST | /api/v1/auth/logout/ | Bearer access + same user's refresh |
| GET/PATCH | /api/v1/users/me/ | Authenticated account |
| POST | /api/v1/users/me/change-password/ | Authenticated, current password required |
| GET | /api/v1/admin/users/ | Active superuser only |
| GET/PATCH | /api/v1/admin/users/{uuid}/ | Active superuser only; update profile/is_active |

No DELETE in admin API; deactivate instead. No arbitrary ID fetch in /users/me/. Normal users cannot enumerate or modify other users.

## Security & deployment

- Access JWT: 5 minutes; refresh JWT: 1 day; refresh rotation and blacklist enabled. Logout blacklists supplied refresh only. Access tokens remain valid until expiration unless the account becomes inactive or password changes.
- Password change and login validate input; generic auth failures to avoid account enumeration.
- DRF scoped throttles limit auth requests in development. **Built-in throttles using Django LocMemCache are per-process and do not provide reliable protection against distributed brute-force or abuse.** Configure a shared cache and edge-layer rate controls before production; include them in readiness/security review.
- `ALLOW_PUBLIC_REGISTRATION=false` by default. If enabled, add email verification, anti-bot and abuse protection according to project needs.
- Bearer tokens should normally stay in memory, not localStorage. If using cookies, configure CSRF/SameSite and refresh-token cookie policy separately.
- JWT implementation uses `djangorestframework-simplejwt`; verify against Django 6.1 in CI, because upstream's published supported matrix may lag the Django release.
- Production password reset and sending email are not implemented. Configure email delivery and audited single-use expiring tokens in a later PR.
- Do not use a new login flow as authentication proof without running tests on PostgreSQL.

## Trade-offs

JWT enables simple separated frontend/backend, but refresh rotation and revocation need a DB-backed blacklist. Traditional Django sessions can be preferable for same-origin apps and let server revoke sessions centrally. This kit includes both backends and leaves client-specific authentication policy configurable.

## Tests

Registration off/on; weak passwords; mass assignment; email normalization and uniqueness; login generic failure; inactive user; profile isolation; superuser-only admin endpoints; refresh blacklist; logout ownership; password change invalidates old tokens; PostgreSQL migrations and smoke tests.
