# Notifications (email) and account recovery

## Why an independent notifications app?

`users` owns identity and generates tokens. `apps.notifications` owns message rendering and email delivery. Other business apps can call the transport without importing Users. The v0.1 module does not store delivery records, attempt retries or run Celery. Future channels (in-app, SMS, push) must be separate adapters; do not assume all channels have the same guarantees.

Django **6.1 MAILERS** is used rather than deprecated `EMAIL_BACKEND` configuration.

## Settings

- `AUTH_EMAIL_FLOWS_ENABLED=false` (default): all recovery/verification routes return 503. Public registration is also prevented when email delivery is disabled.
- `ALLOW_PUBLIC_REGISTRATION=false` (default).
- `AUTH_REQUIRE_EMAIL_VERIFICATION=true`: all JWT and DRF session-authenticated requests require verified identity.
- `AUTH_VERIFICATION_URL` and `AUTH_PASSWORD_RESET_URL`: **trusted, server-configured frontend callback URLs**. The server appends `uid` and `token` query params. The frontend must POST them to the relevant confirmation API, then remove them from browser history and avoid third-party scripts/referrers on this page.
- `PASSWORD_RESET_TIMEOUT=3600`: Django token expiration (seconds) shared by verification and password reset.
- `DEFAULT_FROM_EMAIL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS` / `SMTP_USE_SSL`: production email configuration. Production rejects enabled email flows without SMTP and HTTPS callback URLs.
- Email requests have a separate 3/hour throttle scope from token confirmation (10/min); both are per-cache and require shared/edge controls in production.
- Development: mailer prints links to application console. These links are authentication secrets — **never log real tokens in production**.

## API

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/api/v1/auth/email/resend/` | `{"email":"..."}` -> 202 generic |
| POST | `/api/v1/auth/email/verify/` | `{"uid":"...","token":"..."}` -> 204 or 400 |
| POST | `/api/v1/auth/password/reset/request/` | `{"email":"..."}` -> 202 generic |
| POST | `/api/v1/auth/password/reset/confirm/` | `{"uid":"...","token":"...","new_password":"..."}` -> 204 or 400 |

Registration issues an unverified account and attempts verification delivery synchronously; delivery failure rolls back account creation with HTTP 503. This is deliberately simple for Starter v0.1, not a transactional outbox. A rare commit failure **after successful email send** can produce an invalid link. Add an outbox before implementing high-volume or queued email workloads.

Verification token binds user identity, password, email and verification state; after verification the token is unusable. Password reset uses Django's default token generator, invalidated after password change. Existing access and refresh JWTs become invalid once the password hash changes because of the existing SimpleJWT password-revocation checks.

## Threat model / production blockers

OWASP guidance: responses to existing/missing account requests are identical, tokens are signed, scoped to their use, short-lived and invalidated after use. Still, **synchronous email sending can leak account existence via timing** and DRF per-process LocMemCache throttling is insufficient for abuse protection. Production public registration/reset must include shared/edge rate-limiting, abuse protection and delivery monitoring, plus an asynchronous delivery path if timing non-enumeration is required.

Password reset does **not** verify email, and no new role/permission flags can be accepted via recovery APIs. Changing primary email address is a separate, security-critical flow not included here; copied client projects must not expose arbitrary email edits or bulk email updates that preserve `email_verified`.

Django Console Mailer must only be used on local projects. In production use SMTP on TLS with actual sender/DNS/SPF/DKIM/DMARC configuration. Do not send recovery links via notification channels such as SMS unless evaluated separately.

## Migration policy

`users.User.email_verified` is a **new model field**. In a brand-new project generate initial `users` migration. Existing projects with real accounts need a deliberate migration/backfill strategy, preserving verified status for accounts with proven verified email ownership. Do not treat a pre-existing email as verified without evidence.

No migration is needed for `notifications` v0.1 because it contains no database models.
