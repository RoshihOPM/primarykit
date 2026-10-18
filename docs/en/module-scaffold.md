# Source module scaffold and dependency graph (#52)

**Language:** English · [Source reference (EN)](../module-scaffold.md) · [Docs index](README.md)

The `scripts/module_scaffold.py` CLI runs only in the **PrimaryKit source catalog**. Generated clients do not carry the source module scaffold. It never installs packages, runs Django, creates migrations or deploys.

```bash
python scripts/module_scaffold.py create reviews --requires users --dry-run
python scripts/module_scaffold.py create reviews --requires users
python scripts/module_scaffold.py graph --format json
python scripts/module_scaffold.py graph --format dot > module-graph.dot
```

A safe `create` action adds `apps/reviews/__init__.py`, `apps.py`, `manifest.py` and starter tests. It rejects invalid Python identifiers, missing declared dependencies, already-existing directories and symlinks; it never overwrites an existing source module. Dry-run produces only a JSON file plan. Failed partial writes are cleaned up.

The graph tool parses **manifest AST literals** without importing modules or connecting to the database. JSON includes hard and optional dependencies; DOT uses solid lines for hard and dashed lines for optional references. Hard-dependency cycles are errors.

The generated directory is a **scaffold, not a complete application**: define ownership, permissions, domain models, API routes, business rules and tests yourself. Later generate/review/commit migrations in each detached client.

[Detailed source reference](../module-scaffold.md).
