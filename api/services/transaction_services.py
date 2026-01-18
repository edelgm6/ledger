"""
Transaction service layer for business logic and database operations.

All transaction-related business logic and database writes should go through
these service functions. Services are pure functions with no HTTP dependencies.
"""

import datetime
from dataclasses import dataclass
from decimal import Decimal
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


@dataclass
class LinkResult:
    """Result of linking two transactions."""
    success: bool
    transaction1: Optional[Transaction] = None
    transaction2: Optional[Transaction] = None
    error: Optional[str] = None


def filter_transactions(
    is_closed: Optional[bool] = None,
    has_linked_transaction: Optional[bool] = None,
    transaction_types: Optional[List[str]] = None,
    accounts: Optional[List[Account]] = None,
    date_from: Optional[datetime.date] = None,
    date_to: Optional[datetime.date] = None,
    related_accounts: Optional[List[Account]] = None,
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

    Returns:
        TransactionFilterResult with transactions and count
    """
    queryset = Transaction.objects.filter_for_table(
        is_closed=is_closed,
        has_linked_transaction=has_linked_transaction,
        transaction_types=transaction_types,
        accounts=accounts,
        date_from=date_from,
        date_to=date_to,
        related_accounts=related_accounts,
    ).select_related("account", "suggested_account")

    transactions = list(queryset)
    return TransactionFilterResult(
        transactions=transactions,
        count=len(transactions)
    )


@db_transaction.atomic
def create_transaction(
    date: datetime.date,
    account: Account,
    amount: Decimal,
    description: str,
    suggested_account: Optional[Account] = None,
    transaction_type: Optional[str] = None,
) -> TransactionResult:
    """
    Creates a new transaction.

    Args:
        date: Transaction date
        account: Source account
        amount: Transaction amount (positive or negative)
        description: Transaction description
        suggested_account: Optional suggested offsetting account
        transaction_type: Transaction type (income, purchase, etc.)

    Returns:
        TransactionResult with created transaction
    """
    try:
        transaction_obj = Transaction.objects.create(
            date=date,
            account=account,
            amount=amount,
            description=description,
            suggested_account=suggested_account,
            type=transaction_type,
        )
        return TransactionResult(success=True, transaction=transaction_obj)
    except Exception as e:
        return TransactionResult(success=False, error=str(e))


@db_transaction.atomic
def update_transaction(
    transaction_id: int,
    date: Optional[datetime.date] = None,
    account: Optional[Account] = None,
    amount: Optional[Decimal] = None,
    description: Optional[str] = None,
    suggested_account: Optional[Account] = None,
    transaction_type: Optional[str] = None,
) -> TransactionResult:
    """
    Updates an existing transaction.

    Only updates fields that are provided (not None).

    Args:
        transaction_id: ID of transaction to update
        date: New date (if provided)
        account: New account (if provided)
        amount: New amount (if provided)
        description: New description (if provided)
        suggested_account: New suggested account (if provided)
        transaction_type: New type (if provided)

    Returns:
        TransactionResult with updated transaction
    """
    try:
        transaction_obj = Transaction.objects.get(pk=transaction_id)

        if date is not None:
            transaction_obj.date = date
        if account is not None:
            transaction_obj.account = account
        if amount is not None:
            transaction_obj.amount = amount
        if description is not None:
            transaction_obj.description = description
        if suggested_account is not None:
            transaction_obj.suggested_account = suggested_account
        if transaction_type is not None:
            transaction_obj.type = transaction_type

        transaction_obj.save()
        return TransactionResult(success=True, transaction=transaction_obj)
    except Transaction.DoesNotExist:
        return TransactionResult(success=False, error="Transaction not found")
    except Exception as e:
        return TransactionResult(success=False, error=str(e))


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


@db_transaction.atomic
def link_transactions(
    transaction1_id: int,
    transaction2_id: int
) -> LinkResult:
    """
    Links two transactions together.

    Creates a bidirectional link between transactions, typically used for
    transfers and payments that appear in multiple accounts.

    Args:
        transaction1_id: ID of first transaction
        transaction2_id: ID of second transaction

    Returns:
        LinkResult with both transactions if successful
    """
    try:
        transaction1 = Transaction.objects.get(pk=transaction1_id)
        transaction2 = Transaction.objects.get(pk=transaction2_id)

        # Create bidirectional link
        transaction1.linked_transaction = transaction2
        transaction2.linked_transaction = transaction1

        # Bulk update for efficiency
        Transaction.objects.bulk_update(
            [transaction1, transaction2],
            ['linked_transaction']
        )

        return LinkResult(
            success=True,
            transaction1=transaction1,
            transaction2=transaction2
        )
    except Transaction.DoesNotExist as e:
        return LinkResult(success=False, error=f"Transaction not found: {str(e)}")
    except Exception as e:
        return LinkResult(success=False, error=str(e))


def apply_autotags_to_transactions(
    transactions: Optional[QuerySet[Transaction]] = None
) -> int:
    """
    Applies autotags to given transactions (or all open transactions).

    Autotags set suggested_account, prefill, type, and suggested_entity
    based on pattern matching rules.

    Args:
        transactions: QuerySet of transactions to tag (defaults to open transactions)

    Returns:
        Count of updated transactions
    """
    if transactions is None:
        transactions = Transaction.objects.filter(is_closed=False)

    Transaction.apply_autotags(transactions)
    Transaction.objects.bulk_update(
        transactions,
        ["suggested_account", "prefill", "type", "suggested_entity"],
    )
    return transactions.count()
