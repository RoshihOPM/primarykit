# PrimaryKit project status

**Language:** English · [Русский](../project-status.md) · [Documentation](README.md)

**Verified 2026-11-02, `main` = `39f743f`:** the [repository](https://github.com/RoshihOPM/primarykit) is public; source version is `0.1.0`. The `apps/` catalog has **38 apps** with manifests (3 baseline, 35 selectable). PrimaryKit is a copy-based Django/DRF backend generator, not a production-certified runtime.

## Implemented

A standalone backend generator, module registry and presets, offline `doctor`, migration planning, a fail-closed opt-in three-way updater for non-contract Python, and API contract checks; identity, access-control, outbox/tasks, CRM and commerce example modules. Each generated client owns its sources, database schema, credentials, deployment and releases. Automated migration of live client databases is not provided; [#88](https://github.com/RoshihOPM/primarykit/issues/88) and [#89](https://github.com/RoshihOPM/primarykit/issues/89) remain open.

## Verified GitHub controls

- [Core CI succeeded](https://github.com/RoshihOPM/primarykit/actions/runs/40822782027) on `39f743f` (2026-10-29), with GitHub-hosted jobs, Docker integration and the nine-case PostgreSQL generated-client matrix. Runner admission is restored ([#99](https://github.com/RoshihOPM/primarykit/issues/99)).
- [Full History Secrets Audit succeeded](https://github.com/RoshihOPM/primarykit/actions/runs/40822782197) on the same commit. An automated scan of fetched refs does **not** attest to unreachable Git objects, copyright ownership or a full manual security review.
- [main ruleset](https://github.com/RoshihOPM/primarykit/rules/25549376) is **Active**, targeting `refs/heads/main`: PRs (squash only), resolved conversations, strict `test` and `scan-history` status checks, no force pushes/deletion or bypass actors. [#67](https://github.com/RoshihOPM/primarykit/issues/67) is closed.
- Quality gates include a 75% combined coverage floor for Orders/Sales/Payments, dependency auditing, selected Ruff security rules, and optional pinned code-quality-tool smoke tests. `dev` shares the `main` file tree; `main` is an ancestor of `dev`.

## Still outstanding

- [#68](https://github.com/RoshihOPM/primarykit/issues/68): **open**. Trusted full-clone reachable/orphaned-object checks, manual review of configs/fixtures/private data, and third-party redistribution rights still lack sign-off.
- [#88](https://github.com/RoshihOPM/primarykit/issues/88): source migration histories and client compatibility require more evidence.
- [#89](https://github.com/RoshihOPM/primarykit/issues/89): limited three-way merging exists; published-version compatibility and stateful historical client upgrades remain unverified.
- No independent whole-code security review, published tagged release, or confirmed production load/failure qualification.

See the [maintainer playbook](../maintainer-playbook.md), [post-publication audit checklist](../pre-public-audit.md), and [security policy](../../SECURITY.md). Green CI is not production certification.

This checkpoint describes the latest verified protected `main`; changes in newer PRs require their own CI evidence.
