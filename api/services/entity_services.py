"""
Service layer for entity-related business logic.

Contains functions for entity balance calculations, history retrieval,
and tagging/untagging operations.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db import transaction as db_transaction
from django.db.models import Case, Count, DecimalField, F, Max, Q, Sum, Value, When
from django.db.models.functions import Abs

from api.models import Account, Entity, JournalEntryItem
from api.services import crud


# Journal-entry items in scope for the Balances/Payables-Receivables tab:
# all liability accounts plus Accounts Receivable.
RELEVANT_ITEMS_Q = (
    Q(account__type=Account.Type.LIABILITY)
    | Q(account__sub_type=Account.SubType.ACCOUNTS_RECEIVABLE)
)


@dataclass
class EntityResult:
    """Result of an entity create/update/delete operation."""
    success: bool
    entity: Optional[Entity] = None
    error: Optional[str] = None


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
    Gets aggregated balances for all entities with liability or accounts
    receivable activity.

    Returns balances ordered by absolute balance (descending), then by
    most recent activity date.
    """
    entities_balances_qs = (
        JournalEntryItem.objects.filter(RELEVANT_ITEMS_Q)
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
    Gets entity balances grouped by account for all liability and accounts
    receivable accounts.

    Returns one GroupedEntityBalances per account, ordered by account name.
    Within each group, rows are ordered by absolute balance (desc), then by
    most recent activity. When hide_zero is True, $0-balance entities are
    excluded from rows but their count is tracked in zero_count.
    """
    zero_eps = Decimal("0.005")

    qs = (
        JournalEntryItem.objects.filter(RELEVANT_ITEMS_Q)
        .exclude(entity__isnull=True)
        .values(
            "account__id",
            "account__name",
            "account__is_closed",
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
        acct_key = (row["account__id"], row["account__name"], row["account__is_closed"])
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
    for (acct_id, acct_name, is_closed), all_rows in raw_groups.items():
        net_balance = Decimal("0.00")
        nonzero_rows = []
        zero_count = 0
        for r in all_rows:
            net_balance += r.balance
            if abs(r.balance) < zero_eps:
                zero_count += 1
            else:
                nonzero_rows.append(r)

        if hide_zero and not nonzero_rows and is_closed:
            continue

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

    Filters to liability and accounts receivable accounts and orders by date.
    Returns items and the first item (for form pre-selection).
    """
    untagged_items = list(
        JournalEntryItem.objects.filter(RELEVANT_ITEMS_Q, entity__isnull=True)
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

    Scoped to liability and accounts receivable accounts. When account_id is
    supplied, history is scoped to that account only. Returns items ordered by
    date with a calculated running balance.
    """
    qs = JournalEntryItem.objects.filter(
        RELEVANT_ITEMS_Q,
        entity__pk=entity_id,
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


# --- Entity CRUD for the Settings page (mirrors account_services) -------------


TAG_USAGE_WINDOW_DAYS = 90


def get_entities() -> List[Entity]:
    """Returns all entities (open first, then alphabetical) annotated with:

    - ``account_count``: number of accounts that default to the entity.
    - ``recent_tag_count``: number of journal entry items tagged with the entity
      whose journal entry dates fall within the last ``TAG_USAGE_WINDOW_DAYS``
      days (a rolling usage metric).

    ``distinct=True`` on both counts keeps them correct despite the cross-join
    between the two related sets.
    """
    cutoff = date.today() - timedelta(days=TAG_USAGE_WINDOW_DAYS)
    return list(
        Entity.objects.annotate(
            account_count=Count("accounts", distinct=True),
            recent_tag_count=Count(
                "journal_entry_items",
                filter=Q(journal_entry_items__journal_entry__date__gte=cutoff),
                distinct=True,
            ),
        ).order_by("is_closed", "name")
    )


ENTITY_FIELDS = ("name", "is_closed")


def save_entity(
    cleaned_data: Dict[str, Any], instance: Optional[Entity] = None
) -> EntityResult:
    """Creates or updates an entity from validated form data.

    The caller (view) validates the form and passes ``form.cleaned_data``;
    ``instance`` is the entity being edited (None to create). Returns an
    EntityResult; on any DB error the transaction rolls back.
    """
    entity, error = crud.save_model(Entity, ENTITY_FIELDS, cleaned_data, instance)
    return EntityResult(success=error is None, entity=entity, error=error)


def delete_entity(entity_id: int) -> EntityResult:
    """Deletes an entity, gracefully blocking when it is still referenced.

    Entities are PROTECT-referenced by amortizations, loans, bill rules, paystub
    values, etc. Rather than 500ing on a ProtectedError, we return a friendly
    message so the UI can display it inline.
    """
    entity, error = crud.delete_model(
        Entity,
        entity_id,
        not_found="Entity not found.",
        protected=lambda e: (
            f"Can't delete '{e.name}' — it's still used by other "
            "records (accounts, amortizations, loans, paystub values, etc.). "
            "Close it instead to archive it."
        ),
    )
    return EntityResult(success=error is None, entity=entity, error=error)
