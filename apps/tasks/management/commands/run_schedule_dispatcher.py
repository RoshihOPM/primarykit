"""Poll recurring schedules and publish their due BackgroundJob rows."""

import time

from django.core.management.base import BaseCommand, CommandError

from apps.tasks.scheduler import fire_due


class Command(BaseCommand):
    help = "Dispatch recurring schedules into the existing Tasks queue (PostgreSQL only)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run one scheduler tick")
        parser.add_argument("--poll-seconds", type=float, default=10.0)
        parser.add_argument("--batch-size", type=int, default=100)

    def handle(self, *args, **options):
        poll = options["poll_seconds"]
        batch = options["batch_size"]
        if not 0.1 <= poll <= 3600 or not 1 <= batch <= 1000:
            raise CommandError("Invalid poll-seconds or batch-size")
        fired = 0
        try:
            while True:
                fired += fire_due(limit=batch)
                if options["once"]:
                    break
                time.sleep(poll)
        except KeyboardInterrupt:
            pass
        self.stdout.write(f"Dispatched {fired} scheduled job(s).")
