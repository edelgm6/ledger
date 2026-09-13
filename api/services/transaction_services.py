"""
Transaction service layer for business logic and database operations.

Services are pure functions with no HTTP dependencies.

Note: transaction creation, updates, and linking are NOT owned by this module.
Creation and updates go through ``TransactionForm``; linking goes through
``Transaction.create_link``, which closes the counterpart. Do not reintroduce
service-layer equivalents without reconciling those semantics first.
"""

import datetime
from dataclasses import dataclass
from typing import List, Optional

from django.db import transaction as db_transaction
from django.db.models import QuerySet

from api.models import Account, Transaction


@dataclass
class TransactionResult:
    """Result of a transaction operation."""
    success: bool
    transaction: Optional[Transaction] = None
    error: Optional[str] = None


@dataclass
class TransactionFilterResult:
    """Result of transaction filtering."""
    transactions: List[Transaction]
    count: int


def build_transaction_queryset(
    is_closed: Optional[bool] = None,
    has_linked_transaction: Optional[bool] = None,
    transaction_types: Optional[List[str]] = None,
    accounts: Optional[List[Account]] = None,
    date_from: Optional[datetime.date] = None,
    date_to: Optional[datetime.date] = None,
    related_accounts: Optional[List[Account]] = None,
    suggested_first: bool = False,
) -> QuerySet:
    """The single definition of "the transactions table queryset".

    Both entry points funnel through here: `filter_transactions` (called with
    explicit kwargs for the unfiltered/default views) and
    `TransactionFilterForm.get_transactions` (called with a bound form's
    cleaned_data). They previously each built this queryset by hand with the
    same eight arguments and had already drifted -- the form omitted
    suggested_account from select_related, so the same page issued an extra
    query per row depending on which entry point rendered it.
    """
    return Transaction.objects.filter_for_table(
        is_closed=is_closed,
        has_linked_transaction=has_linked_transaction,
        transaction_types=transaction_types,
        accounts=accounts,
        date_from=date_from,
        date_to=date_to,
        related_accounts=related_accounts,
        suggested_first=suggested_first,
    ).select_related("account", "suggested_account")


def filter_transactions(
    is_closed: Optional[bool] = None,
    has_linked_transaction: Optional[bool] = None,
    transaction_types: Optional[List[str]] = None,
    accounts: Optional[List[Account]] = None,
    date_from: Optional[datetime.date] = None,
    date_to: Optional[datetime.date] = None,
    related_accounts: Optional[List[Account]] = None,
    suggested_first: bool = False,
) -> TransactionFilterResult:
    """
    Filters transactions based on criteria.

    Uses the Transaction.objects.filter_for_table() queryset method
    with optimized select_related for performance.

    Args:
        is_closed: Filter by closed status (True/False/None for all)
        has_linked_transaction: Filter by linked status
        transaction_types: List of transaction types to include
        accounts: List of accounts to filter by
        date_from: Start date (inclusive)
        date_to: End date (inclusive)
        related_accounts: Filter by related accounts in journal entries
        suggested_first: Sort transactions with a suggested_account first

    Returns:
        TransactionFilterResult with transactions and count
    """
    transactions = list(
        build_transaction_queryset(
            is_closed=is_closed,
            has_linked_transaction=has_linked_transaction,
            transaction_types=transaction_types,
            accounts=accounts,
            date_from=date_from,
            date_to=date_to,
            related_accounts=related_accounts,
            suggested_first=suggested_first,
        )
    )
    return TransactionFilterResult(
        transactions=transactions,
        count=len(transactions)
    )


@db_transaction.atomic
def delete_transaction(transaction_id: int) -> TransactionResult:
    """
    Deletes a transaction.

    This will cascade delete related journal entries and items.

    Args:
        transaction_id: ID of transaction to delete

    Returns:
        TransactionResult indicating success/failure
    """
    try:
        transaction_obj = Transaction.objects.get(pk=transaction_id)
        transaction_obj.delete()
        return TransactionResult(success=True, transaction=transaction_obj)
    except Transaction.DoesNotExist:
        return TransactionResult(success=False, error="Transaction not found")
    except Exception as e:
        return TransactionResult(success=False, error=str(e))
