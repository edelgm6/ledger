"""
Service functions for paystub-related operations.

Contains data fetching logic extracted from views/helpers to maintain
pure function patterns and separation of concerns.
"""
from dataclasses import dataclass
from typing import List

from django.db.models import QuerySet

from api.models import Paystub, PaystubValue, S3File


@dataclass
class PaystubsTableData:
    """Data for rendering the paystubs table."""
    has_pending_jobs: bool
    paystubs: List[Paystub]


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
    has_pending = S3File.objects.filter(analysis_complete__isnull=True).exists()

    if has_pending:
        return PaystubsTableData(has_pending_jobs=True, paystubs=[])

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
    ).select_related("account")

    return PaystubDetailData(paystub_values=paystub_values, paystub_id=paystub_id)
