---
name: feature-delivery
description: Implement a nontrivial Django/DRF feature with an implementation plan, regression tests, validation, code review, failure fixes and pull request. Use when asked to build or change a feature end-to-end.
---

# Feature Delivery

Operate in a task branch. Read repository `AGENTS.md`, existing implementation and relevant architecture/database skills.

1. Define acceptance criteria, API/permissions, invariants, failure paths, smallest viable implementation and tests.
2. For nontrivial logic write tests first or alongside the code; include negative cases, permissions, transactions, idempotency and query counts where relevant.
3. Implement with Django/DRF conventions, no unnecessary generic CRUDService. Prefer small, reviewable changes.
4. Run Ruff, Django checks, pytest and PostgreSQL-specific integration tests when needed.
5. If tests fail, diagnose and fix, rerun. Never skip tests or weaken assertions merely to make CI pass.
6. Review the diff independently for security, backward compatibility, migration safety and unintended side effects. Ask for human approval before production or irreversible actions.
7. Prepare PR summary: behavior, affected API, tests and commands/results, database/migrations, rollout, rollback and risks.

Parallelize only independent read-only design/QA reviews when the agent runtime supports delegation; do not claim subagents ran unless they actually ran. Merge outcomes into one reviewed implementation.
