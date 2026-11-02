# Updating copied modules safely

PrimaryKit clients own their source, migrations and deployment. Start from a
**trusted source checkout with the original Git history**. Upgrade commands are
source-only tools; run them in PrimaryKit, pointing to the independent client.

## Read-only inspections

```bash
python scripts/module_upgrade.py --source . --project ../client-api --json
python scripts/module_upgrade.py --source . --project ../client-api --three-way-plan --json
```

The default report classifies source, local and shared changes. The three-way
plan verifies historical source blobs when available and reports mergeability;
neither command modifies the client.

## Opt-in apply modes

`--apply-safe` copies only non-contract Python updates that do not conflict
with client changes. Any sensitive contract, deletion, unknown baseline or
unresolved conflict aborts the batch. It is not a three-way merge.

`--apply-three-way` supports a **limited** Git-backed three-way merge for
non-contract Python files. It requires a clean client Git feature branch,
a clean source module checkout and verified immutable per-module ancestry.

```bash
git -C ../client-api switch -c chore/primarykit-upgrade
python scripts/module_upgrade.py --source . --project ../client-api --three-way-plan --json
python scripts/module_upgrade.py --source . --project ../client-api --apply-three-way --json
git -C ../client-api diff --check
git -C ../client-api diff
# Review source and API contracts, run client PostgreSQL tests, then commit and open a PR.
```

The apply workflow stages replacements and provenance together, with rollback
for ordinary write failures. Previously accepted byte-identical upstream files
also receive verified baseline metadata when another change in their module
is applied. **This is not a transactional filesystem guarantee after a crash.**
Neither mode commits code, creates PRs, upgrades dependencies, rewrites
client-owned migrations or deploys.

Changes to models, manifests, permissions, business contracts, migrations,
source deletions, unresolved textual conflicts and untrusted history require
manual review. Git merge success does not imply semantic compatibility.

See [three-way plan and boundaries](three-way-upgrade-plan.md),
[bundled migration contract](bundled-migration-contract.md),
and [open lifecycle issue #89](https://github.com/RoshihOPM/primarykit/issues/89).
There are no published, cross-version compatibility-certified releases yet.
