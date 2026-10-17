"""Scoped high-entropy API keys. No HTTP routes or implicit tenant privileges."""

import hashlib
import hmac
import re
import secrets
import uuid
from datetime import timedelta
from types import MappingProxyType

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from apps.core.audit import record_audit_event

from .models import ApiKey

_SCOPE = re.compile(r"^[a-z][a-z0-9_.:-]{1,79}$")
_TOKEN = re.compile(r"^pk_([0-9a-f]{32})\.([A-Za-z0-9_-]{32,100})$")


def _scope_permissions():
    config = getattr(settings, "API_KEY_SCOPE_PERMISSIONS", {})
    if not isinstance(config, dict) or any(
        not isinstance(scope, str)
        or not _SCOPE.fullmatch(scope)
        or not isinstance(permission, str)
        or permission.count(".") != 1
        for scope, permission in config.items()
    ):
        raise ImproperlyConfigured(
            "API_KEY_SCOPE_PERMISSIONS must map scopes to Django permissions"
        )
    return MappingProxyType(config)


def _valid_owner(owner):
    return bool(
        owner
        and getattr(owner, "pk", None)
        and owner.is_active
        and (not getattr(settings, "AUTH_REQUIRE_EMAIL_VERIFICATION", True) or owner.email_verified)
    )


def _validate_scopes(owner, scopes):
    if not isinstance(scopes, (tuple, list)) or not 1 <= len(scopes) <= 16:
        raise PermissionDenied("API key scope grant denied")
    permissions = _scope_permissions()
    if any(
        not isinstance(scope, str)
        or scope not in permissions
        or not owner.has_perm(permissions[scope])
        for scope in scopes
    ) or len(set(scopes)) != len(scopes):
        raise PermissionDenied("API key scope grant denied")


@transaction.atomic
def issue_api_key(*, actor, name: str, scopes: tuple[str, ...], expires_at):
    """Issue to the authenticated actor ONLY; return a one-time token."""
    if not _valid_owner(actor):
        raise PermissionDenied("API key owner must be active and verified")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise ValidationError("Invalid API key name")
    _validate_scopes(actor, scopes)
    now = timezone.now()
    if (
        not isinstance(expires_at, type(now))
        or timezone.is_naive(expires_at)
        or expires_at <= now
        or expires_at > now + timedelta(days=90)
    ):
        raise ValidationError("Expiry must be an aware future datetime within 90 days")
    secret = secrets.token_urlsafe(32)
    item = ApiKey.objects.create(
        owner=actor,
        name=name.strip(),
        scopes=list(scopes),
        expires_at=expires_at,
        secret_digest=hashlib.sha256(secret.encode("ascii")).hexdigest(),
    )
    record_audit_event(
        actor=actor, action="api_keys.issued", target_type="api_keys.ApiKey", target_id=item.pk
    )
    return item, f"pk_{item.pk.hex}.{secret}"


def verify_api_key(raw_token: str, *, required_scope: str):
    """Validate one exact scope and the current user's permission on every request."""
    invalid = AuthenticationFailed("Invalid API key credentials")
    permissions = _scope_permissions()
    if (
        not isinstance(required_scope, str)
        or required_scope not in permissions
        or not isinstance(raw_token, str)
        or len(raw_token) > 150
    ):
        raise invalid
    match = _TOKEN.fullmatch(raw_token)
    if not match:
        raise invalid
    try:
        item = ApiKey.objects.select_related("owner").get(pk=uuid.UUID(hex=match.group(1)))
    except (ApiKey.DoesNotExist, ValueError) as exc:
        raise invalid from exc
    digest = hashlib.sha256(match.group(2).encode("ascii")).hexdigest()
    if not hmac.compare_digest(digest, item.secret_digest):
        raise invalid
    now = timezone.now()
    if item.revoked_at is not None or item.expires_at <= now or not _valid_owner(item.owner):
        raise invalid
    if required_scope not in item.scopes or not item.owner.has_perm(permissions[required_scope]):
        raise invalid
    ApiKey.objects.filter(pk=item.pk).filter(
        Q(last_used_at__isnull=True) | Q(last_used_at__lt=now - timedelta(minutes=10))
    ).update(last_used_at=now)
    return item.owner, item


@transaction.atomic
def revoke_api_key(*, actor, key_id):
    """Revoke only an active authenticated owner's own key (even if caller is staff)."""
    if not _valid_owner(actor):
        raise PermissionDenied("API key access denied")
    try:
        item = ApiKey.objects.select_for_update().get(pk=key_id, owner=actor)
    except (ApiKey.DoesNotExist, ValueError, TypeError) as exc:
        raise PermissionDenied("API key access denied") from exc
    if item.revoked_at is None:
        item.revoked_at = timezone.now()
        item.save(update_fields=["revoked_at"])
        record_audit_event(
            actor=actor, action="api_keys.revoked", target_type="api_keys.ApiKey", target_id=item.pk
        )
    return item


@transaction.atomic
def rotate_api_key(*, actor, key_id, expires_at):
    """Atomically replace a key. For zero-downtime rollout issue then revoke manually."""
    if not _valid_owner(actor):
        raise PermissionDenied("API key access denied")
    try:
        old = ApiKey.objects.select_for_update().get(pk=key_id, owner=actor)
    except (ApiKey.DoesNotExist, ValueError, TypeError) as exc:
        raise PermissionDenied("API key access denied") from exc
    if old.revoked_at is not None or old.expires_at <= timezone.now():
        raise PermissionDenied("API key access denied")
    new, token = issue_api_key(
        actor=actor, name=old.name, scopes=tuple(old.scopes), expires_at=expires_at
    )
    revoke_api_key(actor=actor, key_id=old.pk)
    return new, token
