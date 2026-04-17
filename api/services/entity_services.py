"""
Service layer for entity-related business logic.

Contains functions for entity balance calculations, history retrieval,
and tagging/untagging operations.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional

from django.db import transaction as db_transaction
from django.db.models import Case, DecimalField, F, Max, Sum, Value, When
from django.db.models.functions import Abs

from api.models import Account, Entity, JournalEntryItem


@dataclass
class EntityBalance:
    """Represents an entity's aggregated balance from journal entries."""
    entity_id: int
    entity_name: str
    total_debits: Decimal
    total_credits: Decimal
    balance: Decimal
    last_activity_date: date


@dataclass
class AccountEntityBalance:
    """Entity balance scoped to a specific account."""
    account_id: int
    account_name: str
    entity_id: int
    entity_name: str
    total_debits: Decimal
    total_credits: Decimal
    balance: Decimal


@dataclass
class GroupedEntityBalances:
    """Entity balances for a single account, for grouped display."""
    account_id: int
    account_name: str
    net_balance: Decimal
    rows: List[AccountEntityBalance]
    zero_count: int  # number of $0-balance entities not in rows


@dataclass
class EntityHistoryItem:
    """A journal entry item with its running balance for display."""
    journal_entry_item: JournalEntryItem
    running_balance: Decimal


@dataclass
class EntityHistoryData:
    """Entity history with all items and running balances."""
    items: List[EntityHistoryItem]
    entity_id: int
    entity_name: str = ""
    account_name: Optional[str] = None


@dataclass
class UntaggedItemsData:
    """Untagged journal entry items ready for entity assignment."""
    items: List[JournalEntryItem]
    first_item: Optional[JournalEntryItem]


def get_entities_balances() -> List[EntityBalance]:
    """
    Gets aggregated balances for all entities with accounts receivable activity.

    Returns balances ordered by absolute balance (descending), then by
    most recent activity date.
    """
    entities_balances_qs = (
        JournalEntryItem.objects.filter(
            account__sub_type__in=[
                Account.SubType.ACCOUNTS_RECEIVABLE,
            ]
        )
        .exclude(entity__isnull=True)
        .values("entity__id", "entity__name")
        .annotate(
            total_debits=Sum(
                Case(
                    When(
                        type=JournalEntryItem.JournalEntryType.DEBIT,
                        then=F("amount"),
                    ),
                    default=Value(0),
                    output_field=DecimalField(),
                )
            ),
            total_credits=Sum(
                Case(
                    When(
                        type=JournalEntryItem.JournalEntryType.CREDIT,
                        then=F("amount"),
                    ),
                    default=Value(0),
                    output_field=DecimalField(),
                )
            ),
            balance=F("total_credits") - F("total_debits"),
        )
        .annotate(
            abs_balance=Abs(F("balance")),
            max_journalentry_date=Max("journal_entry__date"),
        )
        .order_by("-abs_balance", "-max_journalentry_date")
    )

    return [
        EntityBalance(
            entity_id=item["entity__id"],
            entity_name=item["entity__name"],
            total_debits=item["total_debits"] or Decimal("0.00"),
            total_credits=item["total_credits"] or Decimal("0.00"),
            balance=item["balance"] or Decimal("0.00"),
            last_activity_date=item["max_journalentry_date"],
        )
        for item in entities_balances_qs
    ]


def get_grouped_entities_balances(hide_zero: bool = True) -> List[GroupedEntityBalances]:
    """
    Gets entity balances grouped by account for all AR-type accounts.

    Returns one GroupedEntityBalances per account, ordered by account name.
    Within each group, rows are ordered by absolute balance (desc), then by
    most recent activity. When hide_zero is True, $0-balance entities are
    excluded from rows but their count is tracked in zero_count.
    """
    zero_eps = Decimal("0.005")

    qs = (
        JournalEntryItem.objects.filter(
            account__sub_type__in=[Account.SubType.ACCOUNTS_RECEIVABLE]
        )
        .exclude(entity__isnull=True)
        .values(
            "account__id",
            "account__name",
            "entity__id",
            "entity__name",
        )
        .annotate(
            total_debits=Sum(
                Case(
                    When(
                        type=JournalEntryItem.JournalEntryType.DEBIT,
                        then=F("amount"),
                    ),
                    default=Value(0),
                    output_field=DecimalField(),
                )
            ),
            total_credits=Sum(
                Case(
                    When(
                        type=JournalEntryItem.JournalEntryType.CREDIT,
                        then=F("amount"),
                    ),
                    default=Value(0),
                    output_field=DecimalField(),
                )
            ),
            balance=F("total_credits") - F("total_debits"),
            abs_balance=Abs(F("balance")),
            last_activity=Max("journal_entry__date"),
        )
        .order_by("account__name", "-abs_balance", "-last_activity")
    )

    raw_groups: dict = {}
    for row in qs:
        acct_key = (row["account__id"], row["account__name"])
        if acct_key not in raw_groups:
            raw_groups[acct_key] = []
        raw_groups[acct_key].append(
            AccountEntityBalance(
                account_id=row["account__id"],
                account_name=row["account__name"],
                entity_id=row["entity__id"],
                entity_name=row["entity__name"],
                total_debits=row["total_debits"] or Decimal("0.00"),
                total_credits=row["total_credits"] or Decimal("0.00"),
                balance=row["balance"] or Decimal("0.00"),
            )
        )

    result = []
    for (acct_id, acct_name), all_rows in raw_groups.items():
        net_balance = Decimal("0.00")
        nonzero_rows = []
        zero_count = 0
        for r in all_rows:
            net_balance += r.balance
            if abs(r.balance) < zero_eps:
                zero_count += 1
            else:
                nonzero_rows.append(r)

        result.append(
            GroupedEntityBalances(
                account_id=acct_id,
                account_name=acct_name,
                net_balance=net_balance,
                rows=nonzero_rows if hide_zero else all_rows,
                zero_count=zero_count if hide_zero else 0,
            )
        )

    return result


def get_untagged_journal_entry_items() -> UntaggedItemsData:
    """
    Gets journal entry items without an assigned entity.

    Filters to accounts receivable sub_type and orders by date.
    Returns items and the first item (for form pre-selection).
    """
    relevant_account_types = [
        Account.SubType.ACCOUNTS_RECEIVABLE,
    ]

    untagged_items = list(
        JournalEntryItem.objects.filter(
            entity__isnull=True, account__sub_type__in=relevant_account_types
        )
        .select_related("journal_entry__transaction")
        .order_by("journal_entry__date")
    )

    first_item = untagged_items[0] if untagged_items else None

    return UntaggedItemsData(items=untagged_items, first_item=first_item)


def get_entity_history(
    entity_id: int, account_id: Optional[int] = None
) -> EntityHistoryData:
    """
    Gets the transaction history for an entity with running balances.

    When account_id is supplied, history is scoped to that account only.
    Returns items ordered by date with a calculated running balance.
    """
    qs = JournalEntryItem.objects.filter(
        entity__pk=entity_id,
        account__sub_type__in=[Account.SubType.ACCOUNTS_RECEIVABLE],
    )
    if account_id is not None:
        qs = qs.filter(account__pk=account_id)

    journal_entry_items = list(
        qs.select_related("journal_entry__transaction", "account", "entity")
        .order_by("journal_entry__date")
    )

    history_items = []
    balance = Decimal("0.00")

    for item in journal_entry_items:
        if item.type == JournalEntryItem.JournalEntryType.DEBIT:
            balance -= item.amount
        else:
            balance += item.amount

        history_items.append(
            EntityHistoryItem(
                journal_entry_item=item,
                running_balance=balance,
            )
        )

    entity_name = (
        journal_entry_items[0].entity.name if journal_entry_items else ""
    )
    account_name = (
        journal_entry_items[0].account.name
        if journal_entry_items and account_id is not None
        else None
    )

    return EntityHistoryData(
        items=history_items,
        entity_id=entity_id,
        entity_name=entity_name,
        account_name=account_name,
    )


@db_transaction.atomic
def untag_journal_entry_item(journal_entry_item_id: int) -> Entity:
    """
    Removes the entity assignment from a journal entry item.

    Returns the entity that was removed (for UI state preservation).
    """
    journal_entry_item = JournalEntryItem.objects.get(pk=journal_entry_item_id)
    entity = journal_entry_item.entity
    journal_entry_item.remove_entity()
    return entity


@db_transaction.atomic
def tag_journal_entry_item(journal_entry_item_id: int, entity_id: int) -> None:
    """
    Assigns an entity to a journal entry item.
    """
    journal_entry_item = JournalEntryItem.objects.get(pk=journal_entry_item_id)
    entity = Entity.objects.get(pk=entity_id)
    journal_entry_item.entity = entity
    journal_entry_item.save()
