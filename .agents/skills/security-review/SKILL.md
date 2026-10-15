---
name: security-review
description: Review Django/DRF API changes for broken authorization (IDOR/BOLA/BFLA), JWT/session authentication, mass assignment, data exposure, injection, SSRF, file uploads, abuse, secrets and deployment security. Use before merging any auth, user, tenant, money or data-sensitive feature.
---

# PrimaryKit Security Review

Act as a defensive security reviewer. Read AGENTS.md and the affected serializers/views/services/querysets. Follow OWASP API Security Top 10 (2023), OWASP Authorization and Authentication Cheat Sheets and Django/DRF security guidance. Do not run live exploits or scan systems without scope approval.

## Mandatory steps

1. Write down actors and authorization matrix (anonymous, owner, other user, staff, superuser, tenant). Deny by default.
2. Trace all paths from user-controlled identifiers to storage, including UUID in URL/body/filter, nested objects and indirect foreign keys. Enforce tenant/owner scoping in queryset **and** permissions for retrieve/update/delete. UUIDs are not access control.
3. For DRF list endpoints, apply queryset filtering: `has_object_permission` is NOT evaluated automatically for list results. For create, check ownership in serializer/service: `has_object_permission` does NOT run on create.
4. Compare writable serializer fields to sensitive fields: `is_staff`, `is_superuser`, role, owner_id, balance, price, approval, user_id, tenant_id, privilege flags and state transitions. Use explicit allowlists, never blindly `fields = "__all__"`.
5. Check every HTTP method, custom action and admin function for broken function-level authorization. Service methods must enforce invariants independently where used outside DRF.
6. Review authentication: generic login/reset responses; password hashing/validation; credential stuffing and brute force protections; JWT audience/issuer/signature algorithm, short access TTL, refresh rotation/revocation, compromised-token handling; CSRF for cookies, secure cookie and CORS settings.
7. Review exposure and input/output: private fields, exception traces, debug mode, logs, SQL injection, unsafe deserialization, XSS, SSRF, arbitrary URL fetches, untrusted callbacks and webhook signatures.
8. Review abuse: registration/reset/login/message/upload throttling and *shared cache or edge controls* in multi-worker production. DRF built-in throttling by itself is not a strong brute-force defense.
9. Review file operations: content and size limits, extension/MIME validation, object-level authorization on download, private storage, presigned URL lifetime and path traversal.
10. Review operational risks: secrets, security headers, TLS/proxy headers, dependency advisories, minimal privileges, audit events, retention and GDPR/PII policies where applicable.
11. Account recovery: check email ownership proof, token purpose, expiration, single-use, invalidation after password/email changes, username enumeration, mail delivery failures, and HTTPS callback URLs. Never accept a caller-supplied redirect URL without strict validation.
12. Add negative tests: user A accessing B's resource, staff elevating roles, cross-tenant list/detail, unauthorized PATCH/DELETE/custom actions, password reset enumeration, token replay, disabled accounts, and concurrent state changes.
13. Report findings by severity with reproduction conditions, impact, specific file/line and minimal remediation. Never claim a vulnerability is fixed without a passing regression test.

## Exit criteria

No unresolved Critical/High findings; tests for each relevant access boundary; changed auth/secret configuration documented; CI green. If deployment requires an external control (edge rate limiting, SMTP, WAF, TLS), mark as a production blocker until configured rather than claiming code alone solves it.

See [security test matrix](references/test-matrix.md).
