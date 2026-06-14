"""
Polls Gmail for utility-bill emails and ingests new ones.

Intended to run on a schedule (Heroku Scheduler). Idempotent: already-ingested
messages are skipped via UtilityBill.source_message_id. Read-only Gmail access.
"""
from django.core.management.base import BaseCommand

from api.models import UtilityBill, UtilityBillRule
from api.services.bill_services import ingest_message
from api.services.gmail_services import build_gmail_service, get_message_text, search_messages


class Command(BaseCommand):
    help = "Fetch utility-bill emails from Gmail and ingest new ones."

    def handle(self, *args, **options):
        # Search each distinct (from_address, subject) once, even when several
        # rules share a vendor; account_number resolves the property afterward.
        search_keys = set(
            UtilityBillRule.objects.values_list("from_address", "subject")
        )
        if not search_keys:
            self.stdout.write("No UtilityBillRule configured; nothing to poll.")
            return

        service = build_gmail_service()
        fetched = new = parsed = unresolved = failed = 0

        for from_address, subject in sorted(search_keys):
            message_ids = search_messages(service, from_address, subject)
            for message_id in message_ids:
                fetched += 1
                email = get_message_text(service, message_id)
                bill = ingest_message(message_id, email)
                if bill is None:
                    continue  # already ingested
                new += 1
                if bill.status == UtilityBill.Status.PARSED:
                    parsed += 1
                elif bill.status == UtilityBill.Status.UNRESOLVED:
                    unresolved += 1
                elif bill.status == UtilityBill.Status.FAILED:
                    failed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"fetched={fetched} new={new} parsed={parsed} "
                f"unresolved={unresolved} failed={failed}"
            )
        )
