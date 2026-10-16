"""Run a dedicated worker: python manage.py run_background_jobs."""

import time

from django.core.management.base import BaseCommand, CommandError

from apps.tasks.services import run_next


class Command(BaseCommand):
    help = "Process internal database-backed jobs. Start separately from the web server."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process at most one job")
        parser.add_argument(
            "--max-jobs", type=int, default=0, help="Stop after N completed attempts"
        )
        parser.add_argument("--poll-seconds", type=float, default=2.0)
        parser.add_argument("--lease-seconds", type=int, default=900)

    def handle(self, *args, **options):
        poll = options["poll_seconds"]
        maximum = options["max_jobs"]
        lease = options["lease_seconds"]
        if poll < 0.1 or maximum < 0 or lease < 30:
            raise CommandError("Invalid poll, max-jobs or lease-seconds")
        count = 0
        try:
            while True:
                processed = run_next(lease_seconds=lease)
                count += int(processed)
                if options["once"] or (maximum and count >= maximum):
                    break
                if not processed:
                    time.sleep(poll)
        except KeyboardInterrupt:
            pass
        self.stdout.write(f"Processed {count} job(s).")
