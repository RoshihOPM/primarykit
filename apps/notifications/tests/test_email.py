from unittest.mock import patch

import pytest
from django.core import mail

from apps.notifications.services import NotificationDeliveryError, send_template_email


def test_templated_mail_is_sent_via_django_mailers():
    send_template_email(
        recipient="user@example.com",
        subject="Account verification",
        template="notifications/email_verification.txt",
        context={"action_url": "https://frontend.example.test/verify-email?token=dummy"},
    )
    assert len(mail.outbox) == 1
    assert "https://frontend.example.test" in mail.outbox[0].body


@pytest.mark.django_db
def test_failed_email_delivery_does_not_swallow_error():
    with patch("apps.notifications.services.send_mail", return_value=0):
        with pytest.raises(NotificationDeliveryError):
            send_template_email(
            recipient="user@example.com",
            subject="Test",
            template="notifications/email_verification.txt",
            context={"action_url": "https://example.test/verify"},
        )
