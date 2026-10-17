"""Purge ended device-session metadata after the configured retention window."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.users.models import DeviceSession


class Command(BaseCommand):
    help = "Permanently delete revoked/expired device-session metadata older than N days."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)

    def handle(self, *args, **options):
        days = options["days"]
        if days < 0:
            raise ValueError("--days must be non-negative")
        cutoff = timezone.now() - timedelta(days=days)
        count, _ = DeviceSession.objects.filter(
            Q(revoked_at__lt=cutoff)
            | Q(revoked_at__isnull=True, expires_at__lt=cutoff)
        ).delete()
        self.stdout.write(f"Purged {count} device session records.")
