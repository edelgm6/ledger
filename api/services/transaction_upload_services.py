"""
Service functions for transaction CSV upload orchestration.

Wraps the CSV import so parsing/import failures become clear, user-facing errors
instead of an unhandled 500. Mirrors the result-dataclass pattern used by
``api/services/paystub_upload_services.py``.
"""
import logging
from dataclasses import dataclass
from typing import Optional

from api.forms import UploadTransactionsForm
from api.models import Account

logger = logging.getLogger(__name__)


@dataclass
class TransactionsUploadResult:
    success: bool
    count: int = 0
    account: Optional[Account] = None
    error: Optional[str] = None


def import_transactions_from_csv(
    form: UploadTransactionsForm,
) -> TransactionsUploadResult:
    """
    Runs a validated ``UploadTransactionsForm``'s import inside error handling.

    The form must already be validated by the caller. Any exception raised while
    parsing/importing the CSV (e.g. unexpected columns or unparseable dates) is
    logged and returned as a user-facing error, so the upload view can always
    render a clear success or error message instead of returning a 500.

    Returns:
        TransactionsUploadResult with the imported ``count`` and ``account`` on
        success, or ``success=False`` and an ``error`` message on failure.
    """
    account = form.cleaned_data["account"]
    try:
        count = form.save()
    except Exception:
        logger.exception("Failed to import transactions from CSV for account %s", account)
        return TransactionsUploadResult(
            success=False,
            error=(
                "We couldn't read that file. Check that it's the CSV exported for "
                "this account and try again."
            ),
        )

    return TransactionsUploadResult(success=True, count=count, account=account)
