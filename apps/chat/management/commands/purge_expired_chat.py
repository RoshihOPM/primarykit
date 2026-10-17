from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.chat.models import Message


class Command(BaseCommand):
    help = "Delete expired private chat message metadata. Run on a fixed schedule."

    def handle(self, *args, **options):
        # Bounded batches avoid locking a very large message table at once.
        total = 0
        while True:
            ids = list(
                Message.objects.filter(expires_at__lte=timezone.now())
                .order_by("expires_at")
                .values_list("pk", flat=True)[:500]
            )
            if not ids:
                break
            deleted, _ = Message.objects.filter(pk__in=ids).delete()
            total += deleted
        self.stdout.write(f"Purged {total} expired chat rows.")
