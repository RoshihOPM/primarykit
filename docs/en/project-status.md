# Current project status

**Language:** English · [Русский](../project-status.md) · [English index](README.md)

**Snapshot:** 2026-10-18. Source version: `0.1.0`. Reviewed merged `main` through commit `1c28c9929bc6601098bf0c8bba847f74145a4916`, including governance, favorites and listing media. Confirm the latest CI result in [GitHub Actions](https://github.com/RoshihOPM/primarykit/actions).

## Implemented and merged

The catalog contains **33 apps** with three baseline modules and 30 selectable ones. Issues **#45–#52** were implemented and merged in PRs #58, #54, #56, #57, #55, #59, #60 and #53 respectively:

| Issue | Implemented capability |
| --- | --- |
| #45 | Shared tenant permission policy adapter in Organizations |
| #46 | Workflow state machine, guarded transitions and optional history |
| #47 | PostgreSQL recurring scheduler with lease fencing and timezone/DST handling |
| #48 | JWT device-session listing, logout and revocation |
| #49 | Atomic owner/tenant usage quotas and idempotent ledger |
| #50 | Opt-in authenticated WebSocket adapter and scope-safe private chat |
| #51 | Privacy retention requests, dry-run, grace windows, legal holds and audit |
| #52 | Source-only module scaffold and dependency graph CLI |

Also merged: opt-in seller-owned moderated `listings` (#63), listing media moderation (#64), private `favorites` and saved searches (#65), plus MIT governance (#66). Existing generated clients must install and migrate selected modules deliberately.

Also merged earlier: preset-aware generator with dry-run, module upgrade reports, OpenAPI compatibility checks, scoped API keys, PostgreSQL idempotency receipts, CSV exchange, PostgreSQL search, HTTPS integration adapter and foundational commerce/infrastructure modules.

## Readiness and gaps

- **Source unit/integration CI:** check the current main commit in GitHub Actions; individual merged PR heads passed their reviews and checks. This does not verify an arbitrary generated client's product requirements or current deployment.
- **Repository visibility:** private in the reviewed snapshot.
- **Public release:** no GitHub Release was published in the reviewed snapshot.
- **Licensing:** MIT is merged into the repository; full-history redistribution rights remain subject to independent review.
- **History security review:** not confirmed; do not treat the presence of `.env.example` or `.gitignore` as proof that old commits contain no secrets.
- **Production:** each client must evaluate correctness, migrations, permissions, financial integration and operations for its own composition.
- **Language coverage:** central onboarding, module overview, architecture, implementation guide and status are bilingual; deeper source docs in `docs/` retain their original RU/EN text.

## Next steps (not yet implemented by this documentation PR)

Complete the history/IP/security audit, enable protection of `main` and release a clearly labelled beta only when the owner approves. Consider stronger production tests of real provider integrations and load/performance budgets before advertising turnkey commerce.

Canonical record of code status is **GitHub main/PR/CI**, not this timestamped snapshot.
