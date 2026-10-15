# Security review matrix

| Risk | Probe | Expected |
|---|---|---|
| IDOR / BOLA | User A GET/PATCH/DELETE User B resource ID | 403 or 404; no mutation |
| Broken function authorization | Non-admin call admin endpoints or change HTTP method | 403/405 |
| Mass assignment | Include is_staff/is_superuser/tenant_id/owner_id in PATCH/POST | Rejected or ignored, no privileged change |
| Cross-tenant list leakage | Tenant A list or filter Tenant B data | Only allowed records |
| Privilege escalation | User creates own admin account / modifies roles | Forbidden |
| Token replay | Refresh after logout or password rotation | Rejected |
| Auth brute force | Repeat login/reset attempts via multiple workers/IPs | Shared/edge protections demonstrably enforced |
| Enumeration | Existing vs non-existing accounts in login/reset | Generic indistinguishable errors |
| Injection / SSRF | Malicious SQL/URL/upload metadata | No execution or internal fetch |
| Sensitive data | API response, schema, logs, exceptions | No passwords/tokens/secrets/hidden PII |

## Maintained references

- OWASP API Security Top 10: https://api-security.owasp.org/editions/2023/en/0x11-t10/
- OWASP Authorization: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP Authentication: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- DRF permissions, queryset vs object checks: https://www.django-rest-framework.org/api-guide/permissions/
- Django security: https://docs.djangoproject.com/en/6.1/topics/security/

Review references before use; they are documentation, not code to execute.
