"""
Service functions for paystub-related operations.

Contains data fetching logic extracted from views/helpers to maintain
pure function patterns and separation of concerns.
"""
from dataclasses import dataclass, field
from typing import List

from django.db.models import QuerySet

from api.models import Paystub, PaystubValue, S3File


@dataclass
class PaystubsTableData:
    """Data for rendering the paystubs table."""
    has_pending_jobs: bool
    paystubs: List[Paystub]
    pending_files: List[S3File] = field(default_factory=list)
    has_active_jobs: bool = False


@dataclass
class PaystubDetailData:
    """Data for rendering paystub detail view."""
    paystub_values: QuerySet[PaystubValue]
    paystub_id: int


def get_paystubs_table_data() -> PaystubsTableData:
    """
    Returns data for the paystubs table.

    Any file that has not reached COMPLETE is listed so the table can show its
    state: PENDING/PROCESSING as work in flight, FAILED with a Retry button.

    Only work actually *in flight* hides the unlinked paystubs, and only until
    it lands. FAILED is a terminal state -- it previously kept the list gated
    forever, so a single un-retried upload hid every unlinked paystub from the
    journal-entry page until someone noticed and retried it.
    """
    unfinished_files = list(
        S3File.objects.exclude(status=S3File.Status.COMPLETE).order_by("pk")
    )
    has_active_jobs = any(
        f.status in (S3File.Status.PENDING, S3File.Status.PROCESSING)
        for f in unfinished_files
    )

    if has_active_jobs:
        return PaystubsTableData(
            has_pending_jobs=True,
            paystubs=[],
            pending_files=unfinished_files,
            has_active_jobs=True,
        )

    paystubs = list(
        Paystub.objects.filter(journal_entry__isnull=True)
        .select_related("document")
        .order_by("title")
    )

    # Failed files (if any) still render, alongside the paystubs rather than
    # instead of them.
    return PaystubsTableData(
        has_pending_jobs=bool(unfinished_files),
        paystubs=paystubs,
        pending_files=unfinished_files,
        has_active_jobs=False,
    )


def get_paystub_detail_data(paystub_id: int) -> PaystubDetailData:
    """
    Returns paystub values for detail view.

    Includes account relation for efficient rendering.
    """
    paystub_values = PaystubValue.objects.filter(
        paystub__pk=paystub_id
    ).select_related("account")

    return PaystubDetailData(paystub_values=paystub_values, paystub_id=paystub_id)
