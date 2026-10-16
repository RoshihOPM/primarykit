"""Run with: celery -A apps.celery_tasks.celery_app:app worker -l INFO."""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

from celery import Celery  # noqa: E402
from django.conf import settings  # noqa: E402

from apps.celery_tasks.config import validate_broker  # noqa: E402

validate_broker(
    broker=getattr(settings, "CELERY_BROKER_URL", ""),
    backend=getattr(settings, "CELERY_RESULT_BACKEND", None),
)

app = Celery("client_backend")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)
