"""Clean old closed-listing media and orphaned private objects, bounded per run."""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.listings.media import private_storage
from apps.listings.models import Listing, ListingImage


class Command(BaseCommand):
    help = "Remove retained closed-ad photos and old unreferenced private blobs."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument("--limit", type=int, default=500)

    def handle(self, *args, **opts):
        days, limit = opts["days"], opts["limit"]
        if days < 1 or not 1 <= limit <= 10000:
            raise CommandError("days >= 1 and 1 <= limit <= 10000 required")
        cutoff = timezone.now() - timedelta(days=days)
        storage = private_storage()
        removed = 0
        candidates = list(
            ListingImage.objects.filter(
                listing__status__in=[
                    Listing.Status.ARCHIVED,
                    Listing.Status.SOLD,
                    Listing.Status.REJECTED,
                ],
                listing__updated_at__lt=cutoff,
            )
            .order_by("pk")
            .values_list("pk", flat=True)[:limit]
        )
        for pk in candidates:
            with transaction.atomic():
                subject = (
                    ListingImage.objects.filter(pk=pk).values_list("listing_id", flat=True).first()
                )
                if subject is None:
                    continue
                listing = Listing.objects.select_for_update().get(pk=subject)
                image = ListingImage.objects.select_for_update().filter(pk=pk).first()
                if image is None:
                    continue
                if (
                    listing.status
                    not in {
                        Listing.Status.ARCHIVED,
                        Listing.Status.SOLD,
                        Listing.Status.REJECTED,
                    }
                    or listing.updated_at >= cutoff
                ):
                    continue
                key = image.private_key
                image.delete()
                transaction.on_commit(lambda name=key: storage.delete(name))
                removed += 1

        # Orphaned objects may result from crashes before DB commit. Only purge
        # old blobs to avoid deleting a concurrent in-flight upload.
        orphaned = 0
        try:
            _, filenames = storage.listdir("listing-photos")
        except FileNotFoundError:
            filenames = []
        for name in filenames:
            if orphaned + removed >= limit:
                break
            path = f"listing-photos/{name}"
            if ListingImage.objects.filter(private_key=path).exists():
                continue
            if storage.get_modified_time(path) >= cutoff:
                continue
            storage.delete(path)
            orphaned += 1
        self.stdout.write(f"Removed {removed} retired records and {orphaned} orphan blobs.")
