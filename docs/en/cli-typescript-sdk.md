# PrimaryKit CLI and TypeScript client (v1)

**Language:** English · [Русский](../cli-typescript-sdk.md)

## Scope and architecture

The CLI is a **portable, standard-library-only Python module** copied into each generated Django backend. It delegates to existing reviewed generator, `doctor`, and installer/updater commands instead of implementing another module registry, migration engine or deployment system.

Run it with `python -m apps.core.cli`, or `uv run python -m apps.core.cli` in an uv-managed environment. **This is not currently an installed global `primarykit` shell executable.**

### Generate a project (from the source repository)

```bash
uv run python -m apps.core.cli new ../crm-api --preset crm --dry-run
uv run python -m apps.core.cli new ../crm-api --preset crm --git-init
```

`new` requires the original catalog's `scripts/new_project.py` and **is unavailable inside detached clients**. Name defaults to the destination's basename and must meet the existing kebab-case naming policy. No migration runs automatically.

### Operate a generated client independently

```bash
cd ../crm-api
python -m apps.core.cli modules list --json
python -m apps.core.cli doctor --strict
python -m apps.core.cli add listings --source ../primarykit --dry-run
python -m apps.core.cli add listings --source ../primarykit
python -m apps.core.cli upgrade --source ../primarykit --dry-run --json
```

The client only needs the source checkout for the **explicit** operations `add` and `upgrade`; neither is a runtime dependency. `add` delegates to `manage.py install_kit_module` and therefore requires client Django dependencies, applies no migrations, and needs a trusted local source. `upgrade` is **always read-only** in this CLI; use reviewed existing updater commands separately for opt-in changes. Never pull unreviewed code or apply production migrations automatically. No shell interpolation is used.

## Generate TypeScript SDK for Vue/React

Generated API types must reflect the **particular client's** installed Django modules and endpoints, not the whole source catalog. The CLI exports that project's local OpenAPI schema with `manage.py spectacular` and runs the frontend's **already-installed** `openapi-typescript` executable. The SDK output is two files:

- `schema.d.ts`: types for concrete API paths, operations and DTOs.
- `client.ts`: `createPrimaryKitClient(baseUrl)` backed by `openapi-fetch`.

Prerequisites: a migrated/configured backend capable of generating its OpenAPI schema, an initialized Node frontend with `package.json`, and locally installed/pinned packages (commit `package-lock.json` or an equivalent lockfile):

```bash
cd ../frontend
npm install openapi-fetch
npm install -D openapi-typescript typescript
cd ../crm-api
python -m apps.core.cli sdk typescript --frontend ../frontend --out src/api --dry-run
python -m apps.core.cli sdk typescript --frontend ../frontend --out src/api
```

Alternatively, pass `--schema path/to/openapi.yaml` or a local JSON schema in the **backend** project; this bypasses Django schema export. Remote OpenAPI URLs are not supported. Dependencies are not installed or downloaded by the Python generator itself; the frontend owns them and their versions.

Example usage in a Vue/React frontend:

```typescript
import { createPrimaryKitClient } from "./api/client";

const api = createPrimaryKitClient(import.meta.env.VITE_API_URL);
const { data, error } = await api.GET("/health/live/");
```

`GET()` paths/types are validated against the *actual* generated schema (some health routes may be intentionally excluded from API schema; use a documented route that is present). Configure authorization middleware, JWT refresh, CSP/CORS, timeouts and error policies in the **client project**. Do not embed or store secrets in generated files. The SDK is a typed transport, not a ready-made UI or business logic.

### Safety and changes

- `--dry-run` produces a plan without writes or executing Django/Node tools.
- `--out` must remain inside the explicitly specified frontend directory; pre-existing `client.ts` or `schema.d.ts` cause failure unless `--force` is provided.
- Export + type generation are staged before publishing output. Failures leave existing SDK files unmodified.
- Re-generate after OpenAPI changes, review the diff, and run `npx tsc --noEmit` in the frontend CI. Breaking API changes can still need manual frontend work.
- Use a trusted frontend: invoking a locally installed Node tool runs code from its dependencies. Pin/review Node dependencies and do not use untrusted schemas with remote `$ref` resolution.

**Boundaries:** no npm package is published, no automatic frontend installation, no automatic backend migration, no production schema mutation, and no coupling to the upstream PrimaryKit at runtime.
