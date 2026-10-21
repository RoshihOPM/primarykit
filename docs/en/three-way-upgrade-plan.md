# Version-aware source updates and reviewed three-way apply

New generated projects record source Git SHA, per-module source refs and
fingerprints in `primarykit-origin.json`. These are audit metadata, not runtime
dependencies. Generate from a trusted Git checkout and retain its full history.

```bash
python scripts/module_upgrade.py --source . --project ../client --three-way-plan --json
# Work on the CLIENT repository; start with committed changes and a feature branch.
git -C ../client switch -c chore/primarykit-module-upgrade
python scripts/module_upgrade.py --source . --project ../client --apply-three-way --json
git -C ../client diff --check
git -C ../client diff
# Commit the client changes, run pytest/PostgreSQL CI, and open a client PR.
```

The opt-in apply refuses dirty client or source trees, the default branch, missing
immutable Git ancestry, ambiguous conflict merges, changed schema contracts,
source deletions, unreviewed module migration histories, unsafe symlink paths
and invalid Python. Clients' independent local changes are preserved.
Client hashes and module ancestry advance to the incoming source version only
after all staged replacements succeed; otherwise changes are rolled back.

This tool **does not create Git commits, push code, open a PR, resolve schema
migrations, or deploy**. It applies only non-contract Python to a reviewable
feature branch. The client owner must review the resulting diff, test with
PostgreSQL, commit and create its own pull request.

Still required for complete #89: true independently tagged SemVer module
releases, read-only reviewed schema adoption across historical baselines and
three-version stateful PostgreSQL upgrade CI. The feature above is a
fail-closed lifecycle milestone, not a production migration mechanism.
