"""Validate broker configuration separately from importing optional Celery."""

from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


def validate_broker(*, broker: str, backend: str | None = None) -> None:
    if not isinstance(broker, str) or not broker:
        raise ImproperlyConfigured("CELERY_BROKER_URL must be configured for Celery workers")
    try:
        parts = urlsplit(broker)
        valid = parts.scheme in {"amqp", "amqps", "pyamqp", "redis", "rediss"} and bool(
            parts.hostname
        )
        if parts.port == 0:
            valid = False
    except ValueError:
        valid = False
    if not valid:
        raise ImproperlyConfigured("CELERY_BROKER_URL must be an AMQP or Redis URL")
    if backend:
        try:
            parsed = urlsplit(backend)
            valid_backend = parsed.scheme in {"redis", "rediss"} and bool(parsed.hostname)
            if parsed.port == 0:
                valid_backend = False
        except ValueError:
            valid_backend = False
        if not valid_backend:
            raise ImproperlyConfigured("CELERY_RESULT_BACKEND must be a Redis URL")
