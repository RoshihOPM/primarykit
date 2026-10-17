"""Account-owned device sessions; never persist raw JWTs, IPs or user agents."""

import uuid
from datetime import datetime, timezone as dt_timezone

from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework_simplejwt.exceptions import InvalidToken

from .models import DeviceSession, User

SESSION_CLAIM = "sid"


def device_metadata(user_agent: str) -> dict[str, str]:
    """Reduce untrusted User-Agent input to a fixed, privacy-safe vocabulary."""
    agent = (user_agent or "")[:512].lower()
    if "edg/" in agent or "edgios/" in agent or "edga/" in agent:
        browser = "Edge"
    elif "firefox/" in agent or "fxios/" in agent:
        browser = "Firefox"
    elif "chrome/" in agent or "crios/" in agent:
        browser = "Chrome"
    elif "safari/" in agent:
        browser = "Safari"
    else:
        browser = "Other"

    if "iphone" in agent or "ipad" in agent or "cpu os" in agent:
        os_name = "iOS"
    elif "android" in agent:
        os_name = "Android"
    elif "windows" in agent:
        os_name = "Windows"
    elif "mac os" in agent or "macintosh" in agent:
        os_name = "macOS"
    elif "linux" in agent:
        os_name = "Linux"
    else:
        os_name = "Other"

    if "ipad" in agent or "tablet" in agent:
        device_type = "tablet"
    elif "mobile" in agent or "iphone" in agent or "android" in agent:
        device_type = "mobile"
    elif os_name in {"Windows", "macOS", "Linux"}:
        device_type = "desktop"
    else:
        device_type = "unknown"
    return {"browser": browser, "os": os_name, "device_type": device_type}


def expires_at(refresh) -> datetime:
    return datetime.fromtimestamp(refresh["exp"], tz=dt_timezone.utc)


def create_session(*, user: User, refresh, user_agent: str) -> DeviceSession:
    session = DeviceSession.objects.create(
        user=user,
        expires_at=expires_at(refresh),
        **device_metadata(user_agent),
    )
    refresh[SESSION_CLAIM] = str(session.pk)
    return session


def locked_session(*, user: User, refresh) -> DeviceSession:
    """Only call inside atomic(), after locking the account row."""
    try:
        session_id = uuid.UUID(str(refresh[SESSION_CLAIM]))
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidToken("Token is invalid or expired.") from exc
    session = (
        DeviceSession.objects.select_for_update()
        .filter(pk=session_id, user=user, revoked_at__isnull=True, expires_at__gt=timezone.now())
        .first()
    )
    if session is None:
        raise InvalidToken("Token is invalid or expired.")
    return session


@transaction.atomic
def revoke_one(*, user: User, session_id: uuid.UUID) -> None:
    User.objects.select_for_update().get(pk=user.pk)
    session = (
        DeviceSession.objects.select_for_update()
        .filter(pk=session_id, user_id=user.pk)
        .first()
    )
    if session is None:
        raise Http404
    if session.revoked_at is None:
        session.revoked_at = timezone.now()
        session.save(update_fields=["revoked_at"])


@transaction.atomic
def revoke_all(*, user: User) -> None:
    User.objects.select_for_update().get(pk=user.pk)
    DeviceSession.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )


def revoke_on_password_change(*, user: User) -> None:
    """Called with the account row locked in the caller's transaction."""
    DeviceSession.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )
