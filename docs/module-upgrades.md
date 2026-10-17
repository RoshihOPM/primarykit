# Safe source-copy upgrades

PrimaryKit projects are independent copies of source code. Upgrades are **reviewed
client pull requests**, not automatic `pip update`, database migrations, deployment
or overwrites of client code.

Newly generated clients record SHA-256 snapshots of copied Python files in
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
OpenAPI before applying the change. Older clients without fingerprints must use
manual Git history and diff; do not fabricate a baseline.

Run client-owned migration review, schema checks and security regression tests.
See [module compatibility](module-compatibility.md) and [deployment](deployment.md).
