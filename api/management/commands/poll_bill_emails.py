"""
Polls Gmail for utility-bill emails and ingests new ones.

Intended to run on a schedule (Heroku Scheduler). Idempotent: already-ingested
messages are skipped via UtilityBill.source_message_id. Read-only Gmail access.
"""
from django.core.management.base import BaseCommand

from api.services.bill_services import poll_bill_emails


class Command(BaseCommand):
    help = "Fetch utility-bill emails from Gmail and ingest new ones."

    def handle(self, *args, **options):
        result = poll_bill_emails()
        self.stdout.write(
            self.style.SUCCESS(
                f"fetched={result.fetched} new={result.new} "
                f"parsed={result.parsed} unresolved={result.unresolved} "
                f"failed={result.failed} retried={result.retried} "
                f"recovered={result.recovered}"
            )
        )
