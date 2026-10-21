# Safe copied-module updates

PrimaryKit clients own their source and historical migrations. Run the updater
from a **trusted** catalog checkout, not against an unreviewed third-party source.
Commit your client working tree before attempting an update.

```bash
python scripts/module_upgrade.py --source . --project ../client-api
python scripts/module_upgrade.py --source . --project ../client-api --apply-safe
```

The default report is read-only. `--apply-safe` is an **opt-in**, conservative
operation: it only copies non-contract Python source updates into paths whose
client files still match recorded baseline hashes. It refuses the entire batch
when any installed module has local changes, a conflict, a removed upstream
file or a change to a sensitive contract file (including models, services,
permissions and manifests). The baseline hashes are advanced only after a
successful copy. Staging and best-effort rollback handle ordinary write errors.

**Not supported:** three-way merging, dependency upgrades, versioned migrations,
automated schema updates, or running production migrations. Some runtime
changes may require integration tests or new dependencies even when classified
as non-contract. Always review the diff and run generated project tests on
PostgreSQL before deploying. A Git commit is required for robust crash recovery.
