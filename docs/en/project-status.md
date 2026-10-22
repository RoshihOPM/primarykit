# PrimaryKit project status

**Language:** English · [Русский](../project-status.md) · [Documentation](README.md)

**Verified 2026-10-22, `main` = `df8282a`:** the [repository](https://github.com/RoshihOPM/primarykit) is public; source version is `0.1.0`. The `apps/` catalog has **38 apps** with manifests (3 baseline, 35 selectable). PrimaryKit is a copy-based Django/DRF backend generator, not a production-certified runtime.

## Implemented

A standalone backend generator, module registry and presets, offline `doctor`, migration planning, limited opt-in upgrades of non-contract files, and API contract checks; identity, access-control, outbox/tasks, CRM and commerce example modules. Each generated client owns its sources, database schema, credentials, deployment and releases. Automated migration of live client databases is not provided; [#88](https://github.com/RoshihOPM/primarykit/issues/88) and [#89](https://github.com/RoshihOPM/primarykit/issues/89) remain open.

## Verified GitHub controls

- [Core CI succeeded](https://github.com/RoshihOPM/primarykit/actions/runs/39726369491) on `df8282a` (2026-10-22), with actual GitHub-hosted jobs and the PostgreSQL matrix. Runner admission is restored ([#99](https://github.com/RoshihOPM/primarykit/issues/99)).
- [Full History Secrets Audit succeeded](https://github.com/RoshihOPM/primarykit/actions/runs/39726369481) on the same commit. An automated scan of fetched refs does **not** attest to unreachable Git objects, copyright ownership or a full manual security review.
- [main ruleset](https://github.com/RoshihOPM/primarykit/rules/25549376) is **Active**, targeting `refs/heads/main`: PRs (squash only), resolved conversations, strict `test` and `scan-history` status checks, no force pushes/deletion or bypass actors. [#67](https://github.com/RoshihOPM/primarykit/issues/67) is closed.
- Quality gates being strengthened with an initial 75% combined coverage floor for Orders/Sales/Payments, pinned-production-dependency auditing, and selected high-signal Ruff S rules.

## Still outstanding

- [#68](https://github.com/RoshihOPM/primarykit/issues/68): **open**. Trusted full-clone reachable/orphaned-object checks, manual review of configs/fixtures/private data, and third-party redistribution rights still lack sign-off.
- [#88](https://github.com/RoshihOPM/primarykit/issues/88): source migration histories and client compatibility require more evidence.
- [#89](https://github.com/RoshihOPM/primarykit/issues/89): a version-aware, three-way source upgrade workflow is not yet complete.
- No independent whole-code security review, published tagged release, or confirmed production load/failure qualification.

See the [maintainer playbook](../maintainer-playbook.md), [post-publication audit checklist](../pre-public-audit.md), and [security policy](../../SECURITY.md). Green CI is not production certification.

This checkpoint describes **main before newer PRs**; review their actual CI before changing this status.
