"""
Advisory transaction tagging.

Bill/loan matching is best-effort tagging: it sets suggested_account/entity/type
so imported transactions surface pre-filled in the review table. It is never part
of the core write, so a matcher blowing up must never break the operation that
triggered it (a CSV import, the autotag re-apply). This module owns that
isolation invariant in one place so every caller behaves the same.

Two paths:
- tag_transactions: import time, runs every matcher over the new rows.
- rematch_bills: re-runs bill matching over open transactions via
  ``bill_services.rematch_open_transactions``.

Buttons that exist only to rematch (Loans, Utility Bills settings) call the
services' ``rematch_open_transactions`` directly so failures surface to the user.
"""
import logging
from typing import Callable, List

from api.models import Transaction
from api.services import bill_services, loan_services

logger = logging.getLogger(__name__)


def _run_advisory(matcher: Callable[..., int], *args) -> None:
    """Run one matcher, swallowing + logging any failure. Matching is
    best-effort tagging and must never break its caller."""
    try:
        matcher(*args)
    except Exception:
        logger.exception(
            "Advisory matcher %s failed; tagging skipped.", matcher.__name__
        )


def tag_transactions(transactions: List[Transaction]) -> None:
    """Bill and loan matching over newly imported ``transactions``, isolated so
    a matcher failure never breaks the caller."""
    _run_advisory(bill_services.match_transactions_to_bills, transactions)
    _run_advisory(loan_services.match_transactions_to_loans, transactions)


def rematch_bills() -> None:
    """Bill matching over eligible open transactions, isolated so a failure
    never breaks the caller.

    Loans are deliberately not rematched here: loan matching creates schedule
    rows, so it only runs on demand from the Loans settings button.
    """
    _run_advisory(bill_services.rematch_open_transactions)
