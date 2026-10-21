# Versioned source ancestry and three-way planning

New generated projects record a source Git revision, source module refs and
module source versions in `primarykit-origin.json`. These are informational,
not a runtime dependency. Projects generated outside a Git checkout have
missing revision metadata and cannot use the history-aware planner until a
reviewed baseline is established.

From a trusted **full-history** source checkout run:

    python scripts/module_upgrade.py --project ../client --three-way-plan --json

This is read-only. For files edited both upstream and in the client it:
- retrieves the exact historical source blob with `git show`;
- verifies its SHA-256 against the original copy fingerprint;
- runs a dry, three-way `git merge-file` and Python syntax parse;
- reports whether a merge is technically clean or requires human resolution.

Sensitive API/models/services and migration files are never automatically
merged. A clean textual merge is **not** approval to deploy: run unit,
PostgreSQL and API compatibility checks and review all resulting changes.

Still not implemented: applying clean three-way merges, schema upgrades,
per-module independent SemVer releases, automated PR creation and last-three-
release upgrade CI. Issue #89 remains open until those controls are proven.
