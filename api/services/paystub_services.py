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


@dataclass
class PaystubDetailData:
    """Data for rendering paystub detail view."""
    paystub_values: QuerySet[PaystubValue]
    paystub_id: int


def get_paystubs_table_data() -> PaystubsTableData:
    """
    Returns data for paystubs table.

    Checks for pending Textract jobs first. If any exist, returns
    has_pending_jobs=True with empty paystubs list.

    Otherwise returns unlinked paystubs (those without journal entries).
    """
    pending_files = list(
        S3File.objects.filter(analysis_complete__isnull=True).order_by("pk")
    )

    if pending_files:
        return PaystubsTableData(has_pending_jobs=True, paystubs=[], pending_files=pending_files)

    paystubs = list(
        Paystub.objects.filter(journal_entry__isnull=True)
        .select_related("document")
        .order_by("title")
    )

    return PaystubsTableData(has_pending_jobs=False, paystubs=paystubs)


def get_paystub_detail_data(paystub_id: int) -> PaystubDetailData:
    """
    Returns paystub values for detail view.

    Includes account relation for efficient rendering.
    """
    paystub_values = PaystubValue.objects.filter(
        paystub__pk=paystub_id
    ).select_related("account", "entity")

    return PaystubDetailData(paystub_values=paystub_values, paystub_id=paystub_id)
