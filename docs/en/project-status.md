# PrimaryKit project status

**Language:** English · [Русский](../project-status.md) · [Documentation](README.md)

**Verified 2026-10-21:** `RoshihOPM/primarykit` is **public**, on the `main` default branch; the source README identifies version `0.1.0` and **37 source apps** (3 baseline, 34 selectable). This is a developing source catalog, not a production-certified framework.

## Implemented

The default branch contains a standalone Django/DRF backend generator, independent copyable modules, a manifest registry, preset selection, offline project doctor, migration planning, an opt-in safe-file updater and contract checking. Its app catalog includes identity/permissions, storage, task/outbox/webhook infrastructure, CRM building blocks and commerce examples. Generated clients retain ownership of source changes, migrations, infrastructure and releases.

For an exact installed-module list and module constraints see the [source README](../../README.md), [module catalog](modules.md) and [feature limitations](features.md). Source modules are not an integrated production commerce system: Payments does not process real money; Sales does not automatically adjust Inventory; realtime has scaling limits.

## Open publication/security work

| Issue | Current verified limitation |
| --- | --- |
| [#67](https://github.com/RoshihOPM/primarykit/issues/67) | Active `main` protection has **not been independently verified**. Public visibility makes branch protection eligible but does not activate it. The owner must configure and test the actual ruleset. |
| [#68](https://github.com/RoshihOPM/primarykit/issues/68) | Full historical secret, private-data and code-rights audit is **not signed off**. Prior limited inspection and an earlier green automated audit are not equivalent to a complete current full-clone audit. |
| [#99](https://github.com/RoshihOPM/primarykit/issues/99) | GitHub-hosted jobs were blocked by account payment/budget restrictions before execution. Public visibility does not confirm recovery; inspect fresh Core CI and Full History Secrets Audit runs. |

See the [maintainer playbook](../maintainer-playbook.md), [history audit checklist](../pre-public-audit.md), [security policy](../../SECURITY.md), and [GitHub Actions](https://github.com/RoshihOPM/primarykit/actions).

## Release boundaries

- MIT licensing is in the repository, but final third-party rights verification is still required.
- Do not treat a blocked, skipped or unstarted GitHub Actions job as a successful CI run.
- No automatic upgrade of client-owned database migrations is provided; changes need reviewed migration plans.
- A public GitHub repository is **not** the same as a tagged, supported or security-certified release.
- Before a beta release, require current green checks, a protected `main`, signed-off rights/history review and clear limitations.

This status is a dated checkpoint; the canonical source of truth is the live repository, issues, PRs, ruleset and Actions history.
