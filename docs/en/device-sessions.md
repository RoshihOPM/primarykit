# JWT device sessions (#48)

**Language:** English · [Source reference (EN)](../device-sessions.md) · [Docs index](README.md)

`apps/users` creates one `DeviceSession` for each successful account login, scoped to that user. A session is **not** a fingerprint or a durable physical-device identifier. Authentication refresh tokens carry a signed `sid` claim.

| Method | Path under `/api/v1/` | Effect |
| --- | --- | --- |
| GET | `users/me/sessions/` | List the current user's active sessions |
| DELETE | `users/me/sessions/{uuid}/` | Revoke one owned session (204, idempotent) |
| POST | `users/me/sessions/revoke-all/` | Revoke all sessions including the current one |
| POST | `auth/logout/` | Revoke the caller's session and refresh |
| POST | `auth/refresh/` | Validate session and rotate refresh |

Only privacy-safe browser/OS/device categories and timestamps are saved. No raw JWTs, full user agent, IP address or fingerprint are stored by the session module. Service commands lock User before DeviceSession to serialize racing logout/refresh/password changes. Cross-user session IDs return 404 even to privileged users.

**Revocation caveat:** refresh is blocked promptly, while an existing access token remains valid until its short expiry (five minutes by default). Password changes also invalidate access tokens via the password-hash check. Older refresh tokens **without** `sid` are rejected after migration: plan client re-login during rollout.

Schedule `python manage.py purge_device_sessions --days 30` according to client retention policy; SimpleJWT token tables need a separate `flushexpiredtokens` schedule. Changing the token-storage API in custom client code can reintroduce raw token persistence; review it.

Read [complete source contract](../device-sessions.md).
