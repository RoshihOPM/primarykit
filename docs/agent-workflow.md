# Agent Skills and review workflow

This repo vendors **only locally authored guidance**; no third-party skill scripts are installed or executed.

## Skill discovery

Standard `.agents/skills/<skill-name>/SKILL.md` format with required YAML frontmatter. The root `AGENTS.md` sets repository-wide policy; skill files are focused, reusable checklists invoked for appropriate tasks.

- `system-architect`: architecture, API boundaries, integration patterns, ADR.
- `database-architect`: PostgreSQL/Django models, indexes, migrations and transactions.
- `feature-delivery`: implement/test/fix/review workflow.

## Multi-agent workflow (conditional, not an autonomous daemon)

Coordinator scopes the task and delegates *independent* read-only reviews (system and database architecture). Implementation may proceed once decisions are reconciled. QA and code-review agents check a completed diff, with CI as an objective quality gate. Do not let multiple agents edit the same files or run concurrent migrations. This is an **instructional workflow**; a concrete subagent runtime/configuration is not installed by this PR.

## External references evaluated

- Agent Skills spec: https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx
- OpenAI conventions for repo-local skills: https://developers.openai.com/blog/skills-agents-sdk
- Supabase PostgreSQL skill: https://github.com/supabase/agent-skills/tree/main/skills/supabase-postgres-best-practices
- PostgreSQL query-plan docs: https://www.postgresql.org/docs/current/using-explain.html

Prefer the upstream maintained PostgreSQL skill if external installation is approved. It is a **reference**, not an installed executable dependency. Inspect license and full instructions at the chosen commit before importing. Our `database-architect` skill is project-specific and complements it.

## Example feature request

"Implement stock reservation, with tenant-scoped permissions, atomic balance transition, idempotency, concurrent-writer tests, and a PR. Use the system/database architect and feature-delivery skills."

Exit conditions: behavior documented, code reviewed, tests run, migration impact documented, deployment reviewed by human.
