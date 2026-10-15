# Private Storage v0.1

## Boundary

`apps.storage` owns immutable upload metadata, private blob paths, owner authorization, soft deletion and controlled download. `users` provides identities; `audit` is optional via `apps.core.audit`.

This is a reusable **file attachment service**, not a public CDN or direct presigned-upload system.

## Model

`StoredFile`: UUID, owner FK PROTECT, random backend key, original filename, server-detected MIME, byte size, SHA-256, created timestamp, deleted timestamp.

Never return object keys, bucket names or raw direct URLs in normal user API responses. The default owner policy allows only authenticated owners and active superusers. Staff alone cannot access another user's files.

## Routes

- `POST /api/v1/files/`: multipart upload, field `file`.
- `GET /api/v1/files/`: owner's own files (or all for superuser), paginated.
- `GET /api/v1/files/{uuid}/`: metadata for authorized viewer.
- `GET /api/v1/files/{uuid}/download/`: streaming response, private no-store, attachment disposition and nosniff.
- `DELETE /api/v1/files/{uuid}/`: mark deleted, retain underlying object for retention / eventual cleanup.

## Validation

Default max 10 MiB. MIME is guessed from header magic and filename extension, not trusted from multipart `content_type`. Initially PNG/JPEG/WebP/PDF only, with settings allowlist. This is not a fully validating file parser, malware scanner or DLP system: production should add virus scanning, image decoders for dangerous uploads, archive restrictions and request-body limits at Nginx/API gateway.

Random keys are `private/<uuid4>` and never include client filenames.

## Storage backends

Django 6.1 `STORAGES` is the switchboard. `STORAGE_BACKEND=local` uses a private media folder, which the server must not expose publicly. `STORAGE_BACKEND=s3` uses `storages.backends.s3.S3Storage` with a private bucket, file-overwrite disabled and no public ACL. Install `django-storages[s3]` in generated projects that need S3 (e.g., `uv add 'django-storages[s3]'`). Supports AWS S3 and compatible SeaweedFS/MinIO implementations via a configured endpoint. Test S3-compatible providers against actual integration tests.

Do not configure a public bucket or Nginx static media alias. Django serves authorized streams; very large downloads would need a presigned URL or proxy acceleration after verifying ownership.

## Atomicity and deletion

Blob upload precedes a DB `transaction.atomic` that creates metadata and audit event. On metadata/audit failure, the service attempts to delete the newly written blob. This is **compensating cleanup**, not a distributed transaction: storage may fail during compensation, leaving an orphan that needs scheduled cleanup.

Deletion updates metadata and audit together, but deliberately does not delete the blob. A later audited purge/retention workflow will be needed for regulated production use.

## Production checklist

- Persistence: configure S3 or an explicit persistent local volume. Local filesystem spread across multiple API replicas is not suitable for shared files.
- Verify private bucket ACL and block public access, endpoint TLS, key rotation and access credentials.
- Put anti-virus/malware scanner, file retention, audit monitoring and gateway `client_max_body_size` limits in front of public uploads.
- Prevent filename injection and enforce private authenticated downloads, with no long-lived public links.
- App owner must not be inferred from user-supplied upload metadata.
- If using S3, copy corresponding optional package install and lock changes into the new project's `uv.lock`.

## Migrations

At project creation: `makemigrations users audit storage`, `migrate`; commit generated migrations in the new project's Git.
