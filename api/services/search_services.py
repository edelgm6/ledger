"""
Search service layer for searching transactions and bulk-updating JournalEntryItems.

All search-related business logic and database writes go through these service functions.
Services are pure functions with no HTTP dependencies.
"""

import datetime
from dataclasses import dataclass
from typing import List, Optional

from django.db import transaction as db_transaction

from api.models import Account, JournalEntryItem, Transaction
from api.services.transaction_services import TransactionFilterResult


@dataclass
class BulkPreviewResult:
    """Result of previewing a bulk account change."""
    affected_count: int
    from_account: Account
    to_account: Account


@dataclass
class BulkUpdateResult:
    """Result of applying a bulk account change."""
    success: bool
    updated_count: int = 0
    error: Optional[str] = None


def search_transactions(
    description: Optional[str] = None,
    date_from: Optional[datetime.date] = None,
    date_to: Optional[datetime.date] = None,
    accounts: Optional[List[Account]] = None,
    transaction_types: Optional[List[str]] = None,
    is_closed: Optional[bool] = None,
    related_accounts: Optional[List[Account]] = None,
) -> TransactionFilterResult:
    """
    Searches transactions by various criteria.

    Builds a queryset from Transaction.objects, applying filters.
    Uses filter_for_table() for all standard filters including related_accounts,
    then applies additional filters for description.

    Args:
        description: Case-insensitive substring match on transaction description
        date_from: Start date filter (inclusive)
        date_to: End date filter (inclusive)
        accounts: Filter by transaction account
        transaction_types: Filter by transaction type
        is_closed: Filter by closed status
        related_accounts: Filter by related accounts in journal entries

    Returns:
        TransactionFilterResult with matching transactions and count
    """
    queryset = Transaction.objects.filter_for_table(
        is_closed=is_closed,
        transaction_types=transaction_types,
        accounts=accounts,
        date_from=date_from,
        date_to=date_to,
        related_accounts=related_accounts,
    )

    if description:
        queryset = queryset.filter(description__icontains=description)

    queryset = queryset.prefetch_related(
        "journal_entry__journal_entry_items__account",
        "journal_entry__journal_entry_items__entity",
    ).select_related("account")

    transactions = list(queryset)
    return TransactionFilterResult(transactions=transactions, count=len(transactions))


def preview_bulk_account_change(
    transactions: List[Transaction],
    from_account: Account,
    to_account: Account,
) -> BulkPreviewResult:
    """
    Previews how many JournalEntryItems would be affected by a bulk account change.

    Args:
        transactions: List of transactions to scope the change to
        from_account: Account to change FROM
        to_account: Account to change TO

    Returns:
        BulkPreviewResult with affected count and account objects
    """
    transaction_ids = [t.pk for t in transactions]
    affected_count = JournalEntryItem.objects.filter(
        journal_entry__transaction_id__in=transaction_ids,
        account_id=from_account.pk,
    ).count()

    return BulkPreviewResult(
        affected_count=affected_count,
        from_account=from_account,
        to_account=to_account,
    )


@db_transaction.atomic
def apply_bulk_account_change(
    transactions: List[Transaction],
    from_account_id: int,
    to_account_id: int,
) -> BulkUpdateResult:
    """
    Applies a bulk account change to JournalEntryItems.

    Updates all JEIs matching the FROM account within the given transactions
    to use the TO account instead.

    Args:
        transactions: List of transactions to scope the change to
        from_account_id: Account ID to change FROM
        to_account_id: Account ID to change TO

    Returns:
        BulkUpdateResult with count of updated rows
    """
    transaction_ids = [t.pk for t in transactions]
    updated_count = JournalEntryItem.objects.filter(
        journal_entry__transaction_id__in=transaction_ids,
        account_id=from_account_id,
    ).update(account_id=to_account_id)

    return BulkUpdateResult(success=True, updated_count=updated_count)
