"""One reusable email transport for business apps. No queue or persistence in v0.1."""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from .domain import EmailIntent
from .gateways import DjangoEmailGateway

logger = logging.getLogger(__name__)


class NotificationDeliveryError(Exception):
    """The configured mailer did not accept an email for delivery."""


def send_template_email(*, recipient: str, subject: str, template: str, context: dict) -> None:
    """Send plain text via Django 6.1 MAILERS; never log template context or tokens."""
    intent = EmailIntent(
        recipient=recipient, subject=subject, template=template, context=context
    )
    body = render_to_string(intent.template, intent.context)
    try:
        sent = DjangoEmailGateway(sender_func=send_mail).send(
            recipient=intent.recipient,
            subject=intent.subject,
            body=body,
            sender=settings.DEFAULT_FROM_EMAIL,
        )
        if sent != 1:
            raise NotificationDeliveryError("Mailer accepted no messages")
    except Exception as exc:
        logger.error("Transactional email delivery failed", exc_info=False)
        raise NotificationDeliveryError("Email delivery unavailable") from exc
