# AI-assisted development with PrimaryKit

PrimaryKit's output is **independent copied Django source**, not a runtime
framework. Do not ask an agent to copy every optional module into a client.

## Recommended agent handoff

```bash
uv run python scripts/new_project.py ../client-api --name client-api --preset crm --apps workflows
cd ../client-api
python -m apps.core.agent_context --format markdown > agent-brief.md
python -m apps.core.doctor --strict
```

The agent brief is read-only and offline: it includes currently installed
modules, required dependencies, Catalog/Inventory schema modes and test commands.
It does **not** infer domain requirements, grant authorizations or read secrets.

Give the agent `AGENTS.md`, `agent-brief.md`, the relevant existing source
files, and a concrete *domain brief* containing:

1. Business outcome, actors, roles, authorization ownership and explicit exclusions.
2. Models and lifecycle states with invariants (what must never happen).
3. HTTP endpoints, API examples, error contracts and pagination/search boundaries.
4. Data migrations, data ownership, PII retention and production constraints.
5. Tests: happy paths, negative tenant/owner IDOR, races under PostgreSQL,
   generated-project startup and backwards-compatible API changes.

Suggested instruction:

> Read AGENTS.md and the generated agent brief. Implement the business
> capability inside a new client-owned app; reuse only installed PrimaryKit
> modules. Propose interfaces and permission boundaries first. Use pure
> domain rules and transactional services, write tests and client migrations,
> run the mandated checks, open a PR. Do not alter upstream kit, leak tenant
> objects, migrate production, invent credentials or perform a deployment.

An **AI result is a draft, not an approval**. Human review must inspect access
control, concurrency, migrations, secrets, third-party license compliance and
business invariants. The project remains responsible for real provider sandbox
testing. Never claim a feature is production-safe because a mocked test passes.

## Source vs client

The source-only `scripts/module_scaffold.py` creates reusable catalog apps.
Generated clients do not contain source generator scripts: create their business
apps with ordinary Django files or `python manage.py startapp`, then adapt
the structure to the project's existing conventions. Client migrations belong
to that client's Git history.

See [Project generator](project-generator.md), [module development](module-development.md)
and [independent projects](independent-projects.md).
