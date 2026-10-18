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

**The checker never copies, deletes, migrates, imports Django, accesses the
network, or rewrites files.** A `conflict_review` entry requires a manual
three-way merge; `source_update` is only a proposed update, never automatically
safe. Review permissions, ORM indexes, migrations, standalone/tenant modes and
OpenAPI before applying the change. Installing a new trusted module with `install_kit_module` now adds its copied-file\nSHA-256 snapshot and updates `included_apps` atomically. The installer must be\nupdated manually in clients generated from older kit versions. Existing clients\nwith a missing per-module snapshot receive a `baseline_unknown` report entry\nrequiring human review. Do not create a guessed baseline from modified client\nfiles; use Git history and a trusted source checkout to establish ancestry.

Run client-owned migration review, schema checks and security regression tests.
See [module compatibility](module-compatibility.md) and [deployment](deployment.md).
