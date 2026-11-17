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
manual review; the tool never writes such files (see
[accepting reviewed contract changes](#accepting-reviewed-contract-changes)).
Git merge success does not imply semantic compatibility.

A manifest that uses a newer `Module` field (for example `job_handlers`)
requires the same or a newer `apps/core`: with an older core,
`Module(...)` raises `TypeError` at startup and the doctor reports
`invalid_manifest`. Upgrade `apps/core` before or together with the module.
A client `config/settings/base.py` that still registers `outbox.dispatch` /
`privacy.execute` explicitly keeps working unchanged.

## Accepting reviewed contract changes

Without extra flags `--apply-three-way` still refuses every contract file
change (models, services, permissions, manifest, views and similar) and every
changed module whose source ships migrations. The tool **never writes contract
files**, with or without the flags. The flags below only record a human
decision in `primarykit-origin.json`.

1. Produce the read-only report (`--json`, `--three-way-plan`).
2. In a client feature branch a human reads every contract diff and places the
   changes by hand: copy upstream-only files, hand-merge two-sided ones, delete
   files the source deleted. Commit the result.
3. Run the apply, naming the reviewed modules:

```bash
python scripts/module_upgrade.py --source . --project ../client-api \
  --apply-three-way --accept-reviewed tasks kanban \
  --merged-path kanban/services.py \
  --keep-client-migrations tasks --json
```

- `--accept-reviewed MODULE...`: modules whose contract changes are already
  reviewed and placed in the client.
- `--merged-path MODULE/PATH` (repeatable): each hand-merged file of an
  accepted module that intentionally differs from the source.
- `--keep-client-migrations MODULE...`: accepted modules that keep the client
  migration history they already applied (see the
  [bundled migration contract](bundled-migration-contract.md)).

Plain non-contract Python of an accepted module is merged automatically as
before. On success `primarykit-origin.json` advances fingerprints, the
per-module source SHA, the module version (read from `pyproject.toml` of the
source commit, not the working tree) and `module_migration_policies`.

The whole batch is refused, with nothing written, when:

- an upstream contract change has not been placed in the client;
- a file changed on both sides is not confirmed with `--merged-path`;
- a `--merged-path` matches no reviewed two-sided change or names a module
  that is not accepted;
- source ancestry is missing, unrelated or disagrees with recorded
  fingerprints, or the module baseline is unknown;
- a file deleted upstream is still present in the client;
- `primarykit-origin.json` is a symlink, or the source version or client
  `module_versions` cannot be read;
- a `bundled` module's migration history differs and no decision was given.

**What the flags do not do:** they do not check review quality (the tool
trusts the human's statement), do not port `tests/` or non-Python files (these
are outside the fingerprints; port them by hand, or a stale copied test keeps
asserting the old contract), and do not create or apply migrations. After
acceptance the client runs `makemigrations`, review and `migrate` on a
database copy itself.

## What is verified and what is not

`scripts/ci_release_upgrade.py --baseline ID` takes each of the three commits
in `scripts/release_baselines.json`, generates a client with **that commit's
own** generator, creates client-owned migrations, seeds PostgreSQL (a Tasks
job, an Order, a PaymentIntent), commits client customizations and upgrades to
the current catalog through the flow above. It verifies: client edits kept, no
unreviewed source change left, fingerprints match source bytes, the previously
applied migration ledger unchanged, seeded rows intact, `makemigrations
--check`, read-only `migration_adoption --verify-postgres --strict`, doctor,
Django check and the client's pytest suite on PostgreSQL.

Limits of that evidence:

- the scenario's "reviewer" is a script: it copies upstream-only contract
  files, Git-merges two-sided ones and ports unmodified upstream tests and
  agent guidance files. It stands in for a human in CI only;
- baselines are immutable commits of protected `main` pinned by full SHA. No
  Git tag or GitHub release exists yet; these are **not** SemVer releases;
- only `tasks`, `kanban`, `deals`, `inventory` (standalone), `orders` and
  `payments` are covered;
- history contains no schema-changing upgrade yet, so data-migration upgrades
  are unproven; rollback is not exercised;
- tenant/standalone conversion is unsupported.

See [three-way plan and boundaries](three-way-upgrade-plan.md),
[bundled migration contract](bundled-migration-contract.md), and issues
[#89](https://github.com/RoshihOPM/primarykit/issues/89) and
[#88](https://github.com/RoshihOPM/primarykit/issues/88) (both open).
There are no published, cross-version compatibility-certified releases yet,
and no human-run upgrade of a real client has been recorded.
