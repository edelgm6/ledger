"""
Advisory transaction tagging.

Bill/loan matching is best-effort tagging: it sets suggested_account/entity/type
so imported transactions surface pre-filled in the review table. It is never part
of the core write, so a matcher blowing up must never break the operation that
triggered it (a CSV import, the autotag re-apply). This module owns that
isolation invariant in one place so every caller behaves the same.
"""
import logging
from typing import Callable, Iterable, List

from api.models import Transaction
from api.services.bill_services import match_transactions_to_bills
from api.services.loan_services import match_transactions_to_loans

logger = logging.getLogger(__name__)

Matcher = Callable[[Iterable[Transaction]], int]


def _run_advisory(matcher: Matcher, transactions: Iterable[Transaction]) -> None:
    """Run one matcher, swallowing + logging any failure. Matching is
    best-effort tagging and must never break its caller."""
    try:
        matcher(transactions)
    except Exception:
        logger.exception(
            "Advisory matcher %s failed; tagging skipped.", matcher.__name__
        )


def tag_transactions(
    transactions: List[Transaction], *, include_loans: bool = True
) -> None:
    """
    Bill (and, by default, loan) matching over ``transactions``, isolated so a
    matcher failure never breaks the caller.

    Loan matching creates schedule rows and links transactions, so it isn't safe
    to re-run on already-matched transactions; callers that re-tag existing
    transactions pass ``include_loans=False``.
    """
    _run_advisory(match_transactions_to_bills, transactions)
    if include_loans:
        _run_advisory(match_transactions_to_loans, transactions)
