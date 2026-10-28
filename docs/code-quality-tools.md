# Optional clean-code analysis tools

PrimaryKit exposes three **optional, upstream tools** used by the `ub-mode` agent
skill. They are **not** project/runtime dependencies and are not included in
generated Django backends. Installation requires an explicit local command.

| Tool | Purpose | Source / license |
| --- | --- | --- |
| Crapper | Cyclomatic complexity and coverage-adjusted CRAP score | [unclebob/crapper](https://github.com/unclebob/crapper), 0BSD |
| Dryer | Structural duplication candidates | [unclebob/dryer](https://github.com/unclebob/dryer), 0BSD |
| Mutator | Mutation test sites and surviving mutants | [unclebob/mutator](https://github.com/unclebob/mutator), 0BSD |

Exact upstream Git revisions are pinned in `scripts/quality_tools.py`. Review
those commits before updating them. Only sources, not floating branches, are
used for installation. Third-party Python dependencies are resolved during each
explicit install; this is **not** a hermetic dependency lockfile.

## Setup

From a trusted PrimaryKit checkout, with Git and [uv](https://docs.astral.sh/uv/)
installed:

```bash
uv run python scripts/quality_tools.py install
uv run python scripts/quality_tools.py verify
```

The installer clones all three repositories side by side into the ignored
`.quality-tools/` folder, verifies their exact Git SHAs and clean checkouts,
and installs the packages in a **separate** `.quality-tools/venv` environment.
It does not update `pyproject.toml`, `uv.lock`, Django dependencies or project
migrations. It neither auto-updates the sources nor fetches anything when you run
an already-installed tool. Do not blindly re-run `install` on untrusted changes.

## Analysis and reporting

```bash
# Complexity only. No test execution.
uv run python scripts/quality_tools.py crapper --no-coverage apps/orders/services.py

# With coverage: this tool may run the project's test suite.
uv run python scripts/quality_tools.py crapper apps/orders/services.py

# Potential structural duplication, not proof that two domains should be merged.
uv run python scripts/quality_tools.py dryer --threshold 0.82 apps/orders apps/sales

# Safe preview: list mutation sites without invoking tests.
uv run python scripts/quality_tools.py mutator --scan apps/orders/services.py

# Opt-in mutation analysis: limit to a reviewed file and controlled test command.
uv run python scripts/quality_tools.py mutator --max-workers 2 \
  --test-command "uv run pytest -q apps/orders/tests/" \
  apps/orders/services.py
```

The tools create ignored `.metrics/` and `target/` artifacts. If a tool
uses an existing test/coverage report, verify that it refers to the same source
revision and environment. Run true mutation analysis only inside a **throwaway
development checkout and test database**, never against production resources:
mutants execute the test command many times and a test suite may have side
effects. Restrict worker count and path scope to control resource usage.

Tool scores are advisory. Prefer observable regression tests, transactional
safety, tenant isolation, migration compatibility and simple cohesive code over
arbitrary thresholds. Mutation survivors warrant review; do not blindly edit
good domain code to satisfy a tool. The upstream `ub-mode` instructions are
not redistributed here because their repository lacks an explicit license.

## Client portability

Generated clients copy the PrimaryKit agent skill but **do not** copy its
source-side `scripts/` directory or the optional `.quality-tools/` folder.
Clients are independent: they can adopt their own reviewed quality-tool
installation if useful. No hidden dependency on an upstream checkout is
introduced.

## Developer verification

Core CI runs offline tests for the pinned installer, refusal of
tampered checkouts and CLI behavior. An **isolated** GitHub Actions workflow,
`.github/workflows/quality-tools.yml`, installs the pinned upstream tools and
runs read-only Crapper/Dryer reports and a Mutator site scan only when the
integration files change or when manually dispatched. This verifies that
installation actually works, without adding a runtime dependency or executing
full mutation tests. External code is never run by the general Core CI job.
The optional workflow has read-only repository permissions and no secrets.
