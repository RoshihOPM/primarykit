# Device sessions (Users, issue #48)

PrimaryKit maintains one server-side device session per successful JWT login, rather
than treating a browser user-agent or IP as a durable device identifier. Users
manage only their own sessions. Django admin's cookie-backed sessions are separate.

## API

All URLs use the existing /api/v1/ prefix.

| Method | Path | Authentication | Result |
| --- | --- | --- | --- |
| GET | users/me/sessions/ | Authenticated | Paginated active sessions |
| DELETE | users/me/sessions/{uuid}/ | Authenticated owner | 204; idempotent |
| POST | users/me/sessions/revoke-all/ | Authenticated owner | 204; includes caller |
| POST | auth/logout/ | Authenticated + own refresh | Blacklist refresh and revoke session |
| POST | auth/refresh/ | Signed, nonblacklisted refresh with active session | Rotated pair |

List contains only non-revoked, unexpired sessions, newest first, scoped to
the account. Read-only response fields: id (opaque UUID), browser
(Chrome/Firefox/Edge/Safari/Other), os (iOS/Android/Windows/macOS/Linux/Other),
device_type (mobile/tablet/desktop/unknown), created_at, last_seen_at,
expires_at, is_current. is_current derives from the JWT sid claim and is false
for cookie-authenticated requests. Default project pagination applies.

Accessing another account's UUID always yields 404 on DELETE and never
returns that row on GET, including for staff/superusers. Anonymous requests
are denied.

## Tokens, privacy and consistency

DeviceSession is owned by users.User with CASCADE deletion. It stores only
fixed-vocabulary browser/OS/device classifications, timestamps and UUID.
No raw JWT, full User-Agent, IP, signing secret or fingerprint is stored.
The auth endpoints use SessionRefreshToken to keep SimpleJWT OutstandingToken.token
empty while retaining its JTI/expiry/blacklist relationships; upstream's normal
RefreshToken.for_user may persist the encoded token if a client invokes it
directly outside these endpoints. Review custom auth paths accordingly.
The UA parser bounds input length and does not persist untrusted substrings.
Each login is a separate session, even on the same physical device.

Refresh and access tokens include a signed sid UUID. Each refresh checks
JWT signature, expiry, type, SimpleJWT blacklist, active and verified account,
password hash (CHECK_REVOKE_TOKEN), and its own unrevoked, unexpired session.
Rotated tokens retain sid and update expiry/last-seen metadata. Refresh tokens
without sid are rejected, intentionally invalidating older pre-upgrade refresh
tokens. Coordinate re-login on rollout.

**Access-token expiry lag:** logout, single-session and all-session revocation
block refresh immediately, but already issued access JWTs remain valid until
expiry (five minutes by default). Clients must not promise immediate API
lockout. Password changes additionally invalidate access tokens through
CHECK_REVOKE_TOKEN.

PostgreSQL is authoritative; no cache or broker required. Every login/refresh,
logout and revoke command uses transaction.atomic and locks User before
DeviceSession. Refresh checks the blacklist a second time inside the lock,
so competing refreshes cannot both consume a rotated token. Password change
and password reset use the same User lock before revoking sessions. Revoking
a session invalidates all linked refresh tokens through the session check,
even if their individual JTIs are not stored in the blacklist.

Trade-off: the User lock serializes concurrent refreshes/revokes for one account.
Benchmark before using extremely high per-account session concurrency.
SQLite does not enforce PostgreSQL row-lock semantics; run PostgreSQL tests.

## Retention, account deletion and operational setup

- User deletion cascades to DeviceSession. The device history is not orphaned.
- Expired/revoked rows are invisible to the API but remain stored until purged.
  Schedule: python manage.py purge_device_sessions --days 30 (for example daily).
  This removes metadata 30 days after expiry or revocation; select retention per
  client privacy policy. The command does not delete active sessions.
- SimpleJWT outstanding/blacklisted token tables have separate retention:
  schedule its flushexpiredtokens command.
- Audit module history has independent privacy/deletion requirements; review
  separately in generated clients.

## Migration and rollout

PrimaryKit is copy-based and ships no module migration history. Each generated
client must create/review/commit an additive users.DeviceSession migration, run it
before deploying this code, and test against PostgreSQL. Never regenerate an
existing customer's initial migration or auto-migrate production in AppConfig.

Old refresh tokens lack sid and will no longer refresh; warn users to log in
again. Existing OutstandingToken rows from older deployments may already
contain encoded JWTs. Redact those rows separately with a reviewed one-time
migration/cleanup command; dropping the token string does not remove the JTI
blacklist reference, but review client-specific uses of the field first. Avoid mixed API version deployments. Coordinate rollout, backups and
client behavior. Rollback of code alone changes auth security assumptions.

Run: uv sync --locked --all-groups; uv run ruff check .;
uv run ruff format --check .; uv run python manage.py check
--settings=config.settings.test; uv run pytest. Also run generated-project
migration, doctor --strict, and PostgreSQL race tests.
