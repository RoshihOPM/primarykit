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

## Unmerged branch, 2026-11-17

Not part of the `main` checkpoint above; it has **not run** on GitHub Actions.

- Reviewed acceptance of contract changes: `--apply-three-way --accept-reviewed` ([#89](https://github.com/RoshihOPM/primarykit/issues/89)). The tool still never writes contract files; a human places them in a client branch and the tool records the decision in `primarykit-origin.json`.
- Migration history decision at acceptance, `--keep-client-migrations` ([#88](https://github.com/RoshihOPM/primarykit/issues/88)); status `client_owned_history` in `scripts/migration_adoption.py`.
- `scripts/ci_release_upgrade.py` and `scripts/release_baselines.json`: PostgreSQL clients with data are upgraded from three historical `main` commits to the current catalog. All three scenarios passed **locally** on PostgreSQL 16; the `release-upgrades` CI job (PostgreSQL 17) is added on this branch and has not run yet.
- Dependencies: Django 6.1.3 (security fixes), pytest 9.2.0, ruff 0.17.5.

Limits: the scenario's reviewer is scripted; baselines are commits, not published releases; modules are `tasks`, `kanban`, `deals`, `inventory` (standalone), `orders`, `payments`; history has no schema-changing upgrade. #88 and #89 stay open: published tagged releases, human-run upgrades of real clients, data-migration upgrades, more bundled modules, tenant-mode graphs and rollback verification are missing. #68 is untouched. See [updating copied modules](module-updates.md).

This checkpoint describes the latest verified protected `main`; changes in newer PRs require their own CI evidence.
