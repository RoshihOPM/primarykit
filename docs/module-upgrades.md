# Safe source-copy upgrades

PrimaryKit projects are independent copies of source code. Upgrades are **reviewed
client pull requests**, not automatic `pip update`, database migrations, deployment
or overwrites of client code.

Newly generated clients record SHA-256 snapshots of copied runtime Python files (excluding tests and migrations) in
`primarykit-origin.json`. This provenance contains **hashes only**, no secrets,
and is entirely optional at runtime.

From the source repository, after changing the source module catalog:

```bash
python scripts/module_upgrade.py --project ../my-client --json
```

The report compares three states: original copied file digest, current client
digest, and current trusted source digest. It differentiates source-only changes,
client-only customization, and conflicts. Manifest/models/URLs/services/auth files
are marked `contract_review` when changed.

**The default report never modifies files.** Passing `--apply-safe` explicitly
copies only clean source-only non-contract Python files and updates their
recorded hashes. It refuses all contracts, migrations, deletions, conflicts and
client-modified files (see [limitations](en/module-updates.md)). Neither mode
imports Django, accesses the network, or runs migrations. A `conflict_review` entry requires a manual
three-way merge, or the separate opt-in `--apply-three-way` for non-contract
Python; `source_update` is only a proposed update, never automatically
safe. Contract files are never written by any mode: a human places them in a
client branch and records the decision with `--apply-three-way
--accept-reviewed MODULE` ([workflow and limits](en/module-updates.md#accepting-reviewed-contract-changes)). Review permissions, ORM indexes, migrations, standalone/tenant modes and
OpenAPI before applying the change. Installing a new trusted module with `install_kit_module` now adds its copied-file
SHA-256 snapshot, its migration policy and — only for a clean Git source whose
committed files equal the copied bytes — its source commit, and updates
`included_apps` atomically. It validates manifests against the client's own
`apps/core`, refuses symlinks and copies `migrations/` only for `bundled`
modules ([details](en/getting-started.md)). The installer must be
updated manually in clients generated from older kit versions. Existing clients
with a missing per-module snapshot receive a `baseline_unknown` report entry
requiring human review. Do not create a guessed baseline from modified client
files; use Git history and a trusted source checkout to establish ancestry.

Run client-owned migration review, schema checks and security regression tests.
See [module compatibility](module-compatibility.md) and [deployment](deployment.md).
