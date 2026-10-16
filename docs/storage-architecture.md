# Private Storage v0.2 (organization-scoped)

## Boundary

`apps.storage` owns immutable upload metadata, private blob paths, owner authorization, soft deletion and controlled download. `organizations` is required; `users` provides identities and `audit` remains optional.

This is a reusable **file attachment service**, not a public CDN or direct presigned-upload system.

## Model

`StoredFile`: UUID, required organization FK PROTECT, owner FK PROTECT, random backend key, original filename, server-detected MIME, byte size, SHA-256, created timestamp, deleted timestamp.

Never return object keys, bucket names or raw direct URLs in normal user API responses. Active organization membership is mandatory. Organization owners/admins can manage that company's files, while members/managers can manage only their own files. Global superuser status grants no cross-tenant exception.

## Routes

- `POST /api/v1/organizations/{org_id}/files/`: multipart upload, field `file`.
- `GET /api/v1/organizations/{org_id}/files/`: own files (all tenant files for owner/admin), paginated.
- `GET /api/v1/organizations/{org_id}/files/{uuid}/`: metadata for authorized viewer.
- `GET /api/v1/organizations/{org_id}/files/{uuid}/download/`: streaming response, private no-store, attachment disposition and nosniff.
- `DELETE /api/v1/organizations/{org_id}/files/{uuid}/`: mark deleted, retain underlying object for retention / eventual cleanup.

## Validation

Default max 10 MiB. MIME is guessed from header magic and filename extension, not trusted from multipart `content_type`. Initially PNG/JPEG/WebP/PDF only, with settings allowlist. This is not a fully validating file parser, malware scanner or DLP system: production should add virus scanning, image decoders for dangerous uploads, archive restrictions and request-body limits at Nginx/API gateway.

Random keys are `private/<org_id>/<uuid4>` and never include client filenames.

## Storage backends

Django 6.1 `STORAGES` is the switchboard. `STORAGE_BACKEND=local` uses a private media folder, which the server must not expose publicly. `STORAGE_BACKEND=s3` uses `storages.backends.s3.S3Storage` with a private bucket, file-overwrite disabled and no public ACL. The starter now includes `django-storages[s3]` and Boto3 in `uv.lock`. **SeaweedFS 4.48** is the default self-hosted S3 provider. It is enabled via an optional Compose overlay; AWS S3 is still supported by changing the endpoint and credentials.

Do not configure a public bucket or Nginx static media alias. Django serves authorized streams; very large downloads would need a presigned URL or proxy acceleration after verifying ownership.

## Atomicity and deletion

Blob upload precedes a DB `transaction.atomic` that creates metadata and audit event. On metadata/audit failure, the service attempts to delete the newly written blob. This is **compensating cleanup**, not a distributed transaction: storage may fail during compensation, leaving an orphan that needs scheduled cleanup.

Deletion rechecks membership and file authorization under an organization lock, and updates metadata and audit atomically; the blob is retained. A later audited purge/retention workflow will be needed for regulated production use.

## Production checklist

- Persistence: configure S3 or an explicit persistent local volume. Local filesystem spread across multiple API replicas is not suitable for shared files.
- Verify private bucket ACL and block public access, endpoint TLS, key rotation and access credentials.
- Put anti-virus/malware scanner, file retention, audit monitoring and gateway `client_max_body_size` limits in front of public uploads.
- Prevent filename injection and enforce private authenticated downloads, with no long-lived public links.
- The organization and owner must never be assigned from submitted upload metadata. Check membership again within every service-layer write.
- If using S3, copy corresponding optional package install and lock changes into the new project's `uv.lock`.

## Migrations

For a new project, generate migrations for `users storage organizations` (plus selected optional apps), then migrate and commit the generated migration files.

**Breaking upgrade:** the global API has been removed. Existing file rows have no organization. To upgrade a populated client database, first introduce a nullable organization FK; backfill each row to a verified organization using authoritative business records, flag ambiguous records for manual review, and verify there are no nulls or cross-company assignments before enforcing NOT NULL. Coordinate API clients' change to the organization-prefixed routes. Do not let `makemigrations` assign a single default tenant to existing files. Rehearse migration and rollback on a staging snapshot; do not discard previously committed migrations.

## SeaweedFS single-node S3 via Docker Compose

The source and projects including Storage contain `compose.seaweedfs.yaml`. SeaweedFS is a **local/private S3 provider**, not a public object URL or hosted service. It runs `weed mini`, initializes the configured `S3_BUCKET` using the supplied credentials, and persists blobs in the `seaweedfs_data` Docker volume.

For development:

```bash
cp .env.example .env
docker compose -f compose.yaml -f compose.seaweedfs.yaml up -d --build
docker compose -f compose.yaml -f compose.seaweedfs.yaml exec api python manage.py makemigrations users audit storage
docker compose -f compose.yaml -f compose.seaweedfs.yaml exec api python manage.py migrate
```

For production (with unique credentials, configured Django secret, database backup, TLS reverse proxy and media backup):

```bash
docker compose -f compose.prod.yaml -f compose.seaweedfs.yaml up -d --build
```

**Do not expose SeaweedFS port 8333** publicly: the Compose overlay only exposes it inside the application network. Django uses `http://seaweedfs:8333` as a trusted in-cluster endpoint. HTTP is explicitly permitted by `S3_ALLOW_INSECURE_ENDPOINT=true` for this *internal* path only; use HTTPS/mTLS for external or multi-host traffic. Production refuses the development credentials in `.env.example`; replace them with unique secrets.

`weed mini` is a **single-node** storage installation. It is not multi-node HA or automatic replication. Back up the persistent volume and rehearse restores. A multi-node SeaweedFS cluster can replace the container later while Django continues using `django-storages` and S3. The application does not provide a bucket-facing endpoint to end users.

To run real S3 integration tests on the Compose network, ensure migrations exist then execute:

```bash
docker compose -f compose.yaml -f compose.seaweedfs.yaml exec -T -e PRIMARYKIT_SEAWEEDFS_INTEGRATION=1 api uv run pytest --ds=config.settings.postgres_test apps/storage/tests/test_seaweedfs_integration.py
```

The provider-specific smoke test covers actual bucket connectivity, upload, download, owner-only access and soft deletion. Normal SQLite and PostgreSQL unit tests still use the private filesystem fixture.

The project generator removes `compose.seaweedfs.yaml` if you do not select `storage`. Without this overlay, `docker compose up` still uses private local media by default, so optional modules and small projects remain lightweight.
