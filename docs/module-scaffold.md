# Module scaffold and dependency graph (source catalog only)

**Language:** English · [Guide](en/module-scaffold.md) · [Русский индекс](README.md)


`python scripts/module_scaffold.py` is a **source-only** developer CLI. It lives under
`scripts/` and is intentionally absent from independent client backends created by
`scripts/new_project.py`. It does not install packages, generate migrations, run
Django or modify running services.

## Create a new Django module

From the PrimaryKit **source checkout**:

```bash
python scripts/module_scaffold.py create reviews --requires users --dry-run
python scripts/module_scaffold.py create reviews --requires users
```

The CLI creates a new `apps/reviews/` directory containing:

- `__init__.py`
- `apps.py` with a Django `AppConfig`
- `manifest.py` with `Module(name="reviews", requires=("users",))`
- `tests/__init__.py` and `tests/test_reviews.py` (manifest smoke test)

Use lowercase Python identifiers (`review_events`, not `review-events` or a
Python keyword). Required dependencies must already exist in the source
catalog. The entire operation rejects an existing path, including a symlink,
and never overwrites source files. `--dry-run` prints a JSON file plan without
creating any file. A failed write removes files created by that invocation.

**Important:** Scaffolded modules have **no URL registrations, models,
migrations, permissions, database handlers or business behavior**. Define the
boundaries and ownership policy, add explicit routes and tests, then generate
and commit migrations separately in each new client backend. Follow
[module development](module-development.md) and
[module compatibility](module-compatibility.md).

## Visualize dependencies

```bash
python scripts/module_scaffold.py graph --format json
python scripts/module_scaffold.py graph --format dot > module-graph.dot
# Optional, if Graphviz is installed:
dot -Tsvg module-graph.dot -o module-graph.svg
```

JSON includes the sorted `modules` array with `name`, `requires`, and `optional`
fields. DOT draws module-to-dependency edges: solid for hard dependencies and
dashed for optional integrations. Optional targets missing from the current
source checkout do not produce a DOT edge. Missing hard dependencies and
required dependency cycles cause the CLI to fail with a nonzero exit status.

The graph scanner uses **AST literal parsing** of manifests: it never imports
or executes module manifests, starts Django, or connects to the database.
It is a source development tool, not a replacement for
`python -m apps.core.doctor --strict` in a generated client.

## Verification

```bash
uv run pytest apps/core/tests/test_module_scaffold.py
uv run ruff check scripts/module_scaffold.py apps/core/tests/test_module_scaffold.py
uv run ruff format --check scripts/module_scaffold.py apps/core/tests/test_module_scaffold.py
```

These source-only tests are removed by the project generator; client test suites
must not import `scripts.module_scaffold`.
