---
name: ub-mode
description: Apply PrimaryKit's pragmatic Clean Code workflow to Django and Python changes. Use for feature work, bug fixes, refactoring, test design and code review.
---

# ub-mode — PrimaryKit engineering discipline

This is an **original PrimaryKit adaptation** informed by the public
[unclebob/ub-mode](https://github.com/unclebob/ub-mode) project by Robert C. Martin.
It is **not** a verbatim copy or an official release of that skill. The upstream
repository did not publish a redistribution license when this adaptation was
written (2026-10-28). Do not vendor its text or companion tools without a
separate license and security review.

Read `AGENTS.md` and the relevant repository skills first. This skill
complements — and never overrides — PrimaryKit's security, migration, client
ownership, and branch protection requirements.

## 1. Establish correct behavior

- State the user-observable outcome, important invariants and failure modes.
  Check existing code and tests before assuming a redesign is needed.
- For defects, reproduce the failure. Add a focused regression test first when
  feasible, verify that it fails for the expected reason, and then fix the cause.
  If a reliable test cannot be written first, document why and verify the change
  using an appropriate alternate check; do not invent meaningless tests.
- Make the smallest coherent change that satisfies the contract. Prefer deletion
  and simplification over new abstractions. Avoid re-implementing a decision
  already owned by a domain module.
- Define external-input validation at API, task and integration boundaries;
  keep pure business rules in `domain.py` where the existing design permits.
  Treat database, broker, filesystem and third-party responses as untrusted.
- For concurrent mutations, review transaction boundaries, locks, uniqueness
  constraints, idempotency and retry behavior. Do not use SQLite passing tests
  as evidence that PostgreSQL concurrency semantics are correct.

## 2. Improve structure without changing behavior

- Separate domain decisions from ORM, DRF, infrastructure and transport code.
  Avoid circular dependencies and hidden imports across optional modules.
- Choose descriptive names and cohesive functions; refactor only when it
  clarifies a real responsibility or reduces change risk. Do not chase
  arbitrary function-length or abstraction-count targets.
- Remove *harmful* duplication, but do not force unrelated domains into a
  shared helper just because their code looks similar.
- Write assertions about observable results and failure paths, including
  authorization denial, tenant isolation, data retention and rollback.
  Avoid tests that merely mirror internal implementation details.
- When suitable tools are **already available and trusted**, inspect
  complexity, code duplication or mutation-testing reports for modified
  critical paths. CRAP-score, similarity and mutation thresholds from the
  upstream project are *review signals*, not enforced PrimaryKit CI policy.
  Do not install or execute external tools automatically.

## 3. Prove and communicate the change

- Work in short, reviewable increments. For each increment record the issue,
  decision, tests run, results and remaining risk. Never claim checks passed
  if they were not run.
- Run the project-required Ruff, Django, pytest and doctor checks. For schema,
  transaction, tenant or migration changes, also validate generated clients
  against PostgreSQL and verify backward compatibility and retained data.
- Never overwrite a generated client's migration history or source customizations.
  Propose migration adoption and module upgrades as explicit, reviewable work;
  do not run production migrations or destructive operations.
- Open a PR against `dev` in the PrimaryKit repository. Preserve `main`
  protection and required approvals. A green CI run is necessary, not a
  substitute for reviewing security, behavior, performance and deployment risk.
- End with a compact report: root cause, changes, test evidence, limitations,
  rollback plan when relevant, and PR/commit references.

## Relationship to other skills

Use `feature-delivery` for the end-to-end PR workflow; `system-architect`
for boundaries; `database-architect` for data and migration design;
`security-review` for sensitive changes. This skill adds a disciplined
implementation and refactoring checklist, not another framework or runtime
dependency.
