# Module upgrade safety contract (design proposal)

Status: **proposal only**. This document does not claim that three-way upgrades or versioned migrations are implemented. Tracks #89 and #88.

## Ownership and invariant

PrimaryKit copies source into independent client repositories. Client edits always win over automation. No operation may silently overwrite edited client files, rewrite migration history, or apply a schema change. All writes require an explicit opt-in and a clean, reviewable Git worktree.

## Three-way comparison

For each tracked file use three byte-identifiable inputs:

- **B (base):** immutable source bytes from the exact recorded source commit/tag at installation or previous accepted upgrade.
- **L (local):** current client bytes, including modifications.
- **U (upstream):** source bytes at the requested target version.

Classification (including file addition/deletion):

| Case | Action |
| --- | --- |
| L == B, U != B | Candidate upstream-only change; eligible for opt-in apply if non-contract and policy permits |
| U == B, L != B | Keep local; no upstream change |
| L == U | Already converged; no write |
| L != B, U != B, L != U | Three-way merge candidate; conflicts must block writes to that file |
| Base or source provenance unavailable | Refuse automated apply; provide manual instructions |

A textual merge that exits successfully is not proof of semantic correctness: always present the diff and require review. Binary changes, symlinks, path traversal, renamed files, generated secrets, dependencies, model/schema/migration files and executable hooks are never silently merged. Paths must remain inside the client root after canonicalization.

## Source provenance

Record the source repository URL, immutable commit SHA, module identity, module release version, source file path and content hash. Store or pin retrievable immutable base bytes for each installed file. Validate hashes before planning. A tag name alone is insufficient because tags may move.

## Upgrade workflow

1. Read and validate manifest and provenance, reject unsupported versions or modified/dirty Git state for apply.
2. Resolve exact base and target source trees; refuse missing baselines.
3. Produce a **read-only plan** showing upstream-only, local-only, converged, mergeable, conflicted and schema-sensitive paths.
4. For apply, create a clean temporary worktree/branch, apply only explicitly selected and reviewed changes, and run checks. Never modify the current client worktree directly.
5. Refuse unresolved conflicts; do not partially publish a successful upgrade. Emit a reviewable patch or PR for human acceptance.
6. Update provenance only after the proposed changes have been accepted; retain old provenance for rollback/audit.

## Migration boundary (#88)

Model, migration, schema, permissions and data-contract changes require a separate migration plan and PostgreSQL verification. Never generate or execute migrations automatically as part of source upgrade. Existing client migration graphs must remain untouched without an explicit adoption procedure. Test with persisted data and `makemigrations --check --dry-run`.

## Required tests before marking #89 complete

- Upstream-only, local-only, identical and divergent text changes.
- Concurrent edits to the same line and to different lines; deletion/rename and binary files.
- Missing or tampered provenance, source tags moving, invalid module versions.
- Symlinks, path traversal, untrusted source hooks, interrupted apply and dirty worktrees.
- At least three published baseline versions; PostgreSQL-backed generated clients with modified files.
- Schema change refuses auto-apply and requires a reviewed migration plan.

## Delivery milestones

1. Immutable provenance and source-baseline retrieval.
2. Read-only three-way plan with conflict classification and deterministic tests.
3. Explicit clean-worktree opt-in merge with security and rollback tests.
4. Cross-version PostgreSQL migration and client upgrade matrix.

Do not close #89 or #88 based on this design document alone.
