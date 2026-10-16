"""Email ownership verification and password recovery for Users."""

import logging
from urllib.parse import urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.notifications.services import send_template_email

from .domain import may_send_password_reset, may_send_verification
from .tokens import email_verification_token

logger = logging.getLogger(__name__)


def _action_link(configured_url: str, *, user, token: str) -> str:
    parts = urlsplit(configured_url)
    query = urlencode({"uid": urlsafe_base64_encode(force_bytes(user.pk)), "token": token})
    if parts.query:
        query = f"{parts.query}&{query}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def send_verification_email(user) -> None:
    if not may_send_verification(active=user.is_active, verified=user.email_verified):
        return
    token = email_verification_token.make_token(user)
    send_template_email(
        recipient=user.email,
        subject="Verify your email address",
        template="notifications/email_verification.txt",
        context={
            "action_url": _action_link(settings.AUTH_VERIFICATION_URL, user=user, token=token)
        },
    )


def send_password_reset_email(user) -> None:
    if not may_send_password_reset(active=user.is_active):
        return
    token = default_token_generator.make_token(user)
    send_template_email(
        recipient=user.email,
        subject="Reset your password",
        template="notifications/password_reset.txt",
        context={
            "action_url": _action_link(settings.AUTH_PASSWORD_RESET_URL, user=user, token=token)
        },
    )
