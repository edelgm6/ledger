"""
Service functions for statement generation and processing.

Contains business logic for filtering accounts, building statement summaries,
finding unbalanced entries, and calculating metrics. All database writes
go through services with atomic transactions.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from django.db.models import Case, DecimalField, F, Sum, When

from api.models import Account, JournalEntry, JournalEntryItem
from api.statement import (
    Balance,
    BalanceSheet,
    CashFlowStatement,
    EntityBalance,
    IncomeStatement,
)


@dataclass
class SubTypeSummary:
    """Summary for a single account sub_type."""

    name: str
    total: Decimal
    balances: List[Balance]


@dataclass
class AccountTypeSummary:
    """Summary for a single account type (ASSET, LIABILITY, etc.)."""

    name: str
    total: Decimal
    sub_types: List[SubTypeSummary]


@dataclass
class StatementSummary:
    """Hierarchical summary organized by account type/sub_type."""

    account_types: Dict[str, AccountTypeSummary]


@dataclass
class EntitySubTypeSummary:
    """A statement section (sub_type) broken out by entity."""

    name: str
    total: Decimal
    balances: List[EntityBalance]


@dataclass
class EntityIncomeSummary:
    """Income statement summary organized by entity instead of by account.

    Income and expense are each split into their sub_type sections (Salary,
    Operating, Tax, …), and within a section entities are sorted by amount
    descending so the largest sources/uses surface first.
    """

    income_total: Decimal
    income_sub_types: List[EntitySubTypeSummary]
    expense_total: Decimal
    expense_sub_types: List[EntitySubTypeSummary]
    net_income: Decimal


@dataclass
class UnbalancedEntriesResult:
    """Result of finding unbalanced journal entries."""

    entries: List[JournalEntry]
    count: int


@dataclass
class StatementDetailData:
    """Data for statement detail drill-down."""

    journal_entry_items: List[JournalEntryItem]
    account: Optional[Account] = None


@dataclass
class CashFlowMetrics:
    """All cash flow metrics for rendering."""

    operations_flows: List[Balance]
    financing_flows: List[Balance]
    investing_flows: List[Balance]
    cash_from_operations: Decimal
    cash_from_financing: Decimal
    cash_from_investing: Decimal
    net_cash_flow: Decimal
    levered_cash_flow: Decimal
    levered_cash_flow_post_retirement: Decimal
    cash_flow_discrepancy: Optional[Decimal]


def filter_closed_accounts(balances: List[Balance]) -> List[Balance]:
    """
    Filter out closed accounts with $0 balance.

    Pure function - no database access.

    Args:
        balances: List of Balance objects to filter

    Returns:
        List of Balance objects with closed $0-balance accounts removed
    """
    result = []
    for balance in balances:
        # Skip closed accounts with zero balance
        if balance.account.is_closed and balance.amount == 0:
            continue
        result.append(balance)
    return result


def _iter_sub_type_sections(
    balances: List[Any],
    account_type: str,
    sub_type_key: Callable[[Any], str],
) -> Iterator[Tuple[Any, List[Any]]]:
    """Yield ``(sub_type, members)`` for each sub_type of ``account_type``.

    Buckets ``balances`` once by sub_type, then walks
    ``Account.SUBTYPE_TO_TYPE_MAP`` so sections come out in canonical order
    (sub_types with no members yield an empty list). ``sub_type_key`` extracts
    a balance's sub_type value, which differs between the by-account
    (``balance.account.sub_type``) and by-entity (``balance.sub_type``) paths.
    """
    buckets: Dict[str, List[Any]] = {}
    for balance in balances:
        buckets.setdefault(sub_type_key(balance), []).append(balance)

    for sub_type in Account.SUBTYPE_TO_TYPE_MAP[account_type]:
        yield sub_type, buckets.get(sub_type.value, [])


def build_statement_summary(statement: Any) -> StatementSummary:
    """
    Build a hierarchical summary from a statement's balances.

    Pure function - organizes flat balance list into type/sub_type hierarchy.

    Args:
        statement: IncomeStatement, BalanceSheet, or similar with .balances attribute

    Returns:
        StatementSummary with balances organized by type and sub_type
    """
    type_dict = dict(Account.Type.choices)
    account_types: Dict[str, AccountTypeSummary] = {}

    for account_type in Account.Type.values:
        type_total = Decimal("0")
        sub_type_summaries: List[SubTypeSummary] = []

        for sub_type, balances in _iter_sub_type_sections(
            statement.balances, account_type, lambda b: b.account.sub_type
        ):
            sub_type_total = sum(
                (balance.amount for balance in balances), Decimal("0")
            )

            # Filter closed accounts and create sub_type summary
            sub_type_summaries.append(
                SubTypeSummary(
                    name=sub_type.label,
                    total=sub_type_total,
                    balances=filter_closed_accounts(balances),
                )
            )

            type_total += sub_type_total

        # Create account type summary
        label = type_dict[account_type]
        account_types[account_type] = AccountTypeSummary(
            name=label,
            total=type_total,
            sub_types=sub_type_summaries,
        )

    return StatementSummary(account_types=account_types)


def _build_entity_sub_type_summaries(
    balances: List[EntityBalance],
    account_type: str,
) -> List[EntitySubTypeSummary]:
    """Group entity balances into the sections of one account type.

    Walks the type's sub_types in their canonical order, skipping sections with
    no activity. Within each section entities are sorted by amount descending
    so the biggest sources/uses appear first.
    """
    summaries: List[EntitySubTypeSummary] = []
    for sub_type, members in _iter_sub_type_sections(
        balances, account_type, lambda b: b.sub_type
    ):
        if not members:
            continue
        sorted_members = sorted(members, key=lambda b: b.amount, reverse=True)
        total = sum((balance.amount for balance in sorted_members), Decimal("0"))
        summaries.append(
            EntitySubTypeSummary(
                name=sub_type.label, total=total, balances=sorted_members
            )
        )
    return summaries


def build_entity_income_summary(
    income_statement: IncomeStatement,
) -> EntityIncomeSummary:
    """
    Build an income statement summary grouped by entity.

    Splits the statement's entity-level balances into income and expense
    sections (Salary, Operating, Tax, …), breaking each section out by entity
    sorted by amount descending. Net income is income_total - expense_total,
    which reconciles to the by-account income statement's net income.

    Args:
        income_statement: IncomeStatement for the period

    Returns:
        EntityIncomeSummary with per-entity, per-section income/expense totals
    """
    balances = income_statement.get_entity_balances()

    income_sub_types = _build_entity_sub_type_summaries(
        balances, Account.Type.INCOME
    )
    expense_sub_types = _build_entity_sub_type_summaries(
        balances, Account.Type.EXPENSE
    )

    income_total = sum(
        (section.total for section in income_sub_types), Decimal("0")
    )
    expense_total = sum(
        (section.total for section in expense_sub_types), Decimal("0")
    )

    return EntityIncomeSummary(
        income_total=income_total,
        income_sub_types=income_sub_types,
        expense_total=expense_total,
        expense_sub_types=expense_sub_types,
        net_income=income_total - expense_total,
    )


def find_unbalanced_journal_entries() -> UnbalancedEntriesResult:
    """
    Find journal entries where total debits don't equal total credits.

    Database query with aggregation.

    Returns:
        UnbalancedEntriesResult with entries and count
    """
    unbalanced_entries = list(
        JournalEntry.objects.select_related("transaction")
        .annotate(
            total_debits=Sum(
                Case(
                    When(
                        journal_entry_items__type="debit",
                        then=F("journal_entry_items__amount"),
                    ),
                    output_field=DecimalField(),
                )
            ),
            total_credits=Sum(
                Case(
                    When(
                        journal_entry_items__type="credit",
                        then=F("journal_entry_items__amount"),
                    ),
                    output_field=DecimalField(),
                )
            ),
        )
        .exclude(total_debits=F("total_credits"))
    )

    return UnbalancedEntriesResult(
        entries=unbalanced_entries,
        count=len(unbalanced_entries),
    )


def _build_detail_items(
    queryset: Any,
    label_fn: Callable[[JournalEntryItem], str],
) -> List[JournalEntryItem]:
    """Materialize statement detail items with signed amounts and labels.

    Applies the shared select_related/ordering, then sets ``amount_signed``
    (via the account's debit/credit convention) and ``display_label`` (from
    ``label_fn``) on each item.
    """
    journal_entry_items = list(
        queryset.select_related(
            "journal_entry__transaction", "account", "entity"
        ).order_by("journal_entry__date")
    )

    for entry in journal_entry_items:
        entry.amount_signed = entry.get_signed_amount()
        entry.display_label = label_fn(entry)

    return journal_entry_items


def get_statement_detail_items(
    account_id: int,
    from_date: str,
    to_date: str,
) -> StatementDetailData:
    """
    Get journal entry items for an account with signed amounts.

    Applies signing logic:
    - INCOME + DEBIT → negative
    - EXPENSE + CREDIT → negative
    - Others → positive

    Args:
        account_id: The account ID to get items for
        from_date: Start date (string, YYYY-MM-DD)
        to_date: End date (string, YYYY-MM-DD)

    Returns:
        StatementDetailData with signed journal entry items
    """
    journal_entry_items = _build_detail_items(
        JournalEntryItem.objects.filter(
            account__pk=account_id,
            journal_entry__date__gte=from_date,
            journal_entry__date__lte=to_date,
            amount__gt=0,
        ),
        # Prefer the human-readable entity name; fall back to the raw
        # transaction description when the item has no entity.
        label_fn=lambda entry: (
            entry.entity.name
            if entry.entity
            else entry.journal_entry.transaction.description
        ),
    )

    account = journal_entry_items[0].account if journal_entry_items else None

    return StatementDetailData(
        journal_entry_items=journal_entry_items,
        account=account,
    )


def get_statement_detail_items_by_entity(
    entity_id: Optional[int],
    sub_type: str,
    from_date: str,
    to_date: str,
) -> StatementDetailData:
    """
    Get journal entry items for an entity within a statement section.

    Parallels get_statement_detail_items but pivots on entity + account
    sub_type (Salary, Operating, Tax, …). entity_id of None selects the
    Unassigned bucket (items with no entity). Applies the same income-debit /
    expense-credit sign rules, and labels each row with its account name (the
    entity is fixed in this view).

    Args:
        entity_id: The entity ID, or None for the Unassigned bucket
        sub_type: The account sub_type identifying the section
        from_date: Start date (string, YYYY-MM-DD)
        to_date: End date (string, YYYY-MM-DD)

    Returns:
        StatementDetailData with signed journal entry items
    """
    queryset = JournalEntryItem.objects.filter(
        account__sub_type=sub_type,
        journal_entry__date__gte=from_date,
        journal_entry__date__lte=to_date,
        amount__gt=0,
    )
    if entity_id is None:
        queryset = queryset.filter(entity__isnull=True)
    else:
        queryset = queryset.filter(entity__pk=entity_id)

    journal_entry_items = _build_detail_items(
        queryset,
        # The entity is fixed for this view, so surface the account instead.
        label_fn=lambda entry: entry.account.name,
    )

    return StatementDetailData(journal_entry_items=journal_entry_items)


def calculate_cash_flow_metrics(from_date: date, to_date: date) -> CashFlowMetrics:
    """
    Calculate all cash flow metrics for rendering.

    Creates income statement, balance sheets, and cash flow statements
    to extract all required metrics.

    Args:
        from_date: Start date for the period
        to_date: End date for the period

    Returns:
        CashFlowMetrics with all calculated values
    """
    # Create statements for the period
    income_statement = IncomeStatement(end_date=to_date, start_date=from_date)
    end_balance_sheet = BalanceSheet(end_date=to_date)
    start_balance_sheet = BalanceSheet(end_date=from_date + timedelta(days=-1))

    cash_statement = CashFlowStatement(
        income_statement=income_statement,
        start_balance_sheet=start_balance_sheet,
        end_balance_sheet=end_balance_sheet,
    )

    # Create global cash flow statement for discrepancy check
    global_end_date = "2500-01-01"
    global_start_date = "1900-01-01"
    global_cash_statement = CashFlowStatement(
        income_statement=IncomeStatement(
            end_date=global_end_date, start_date=global_start_date
        ),
        end_balance_sheet=BalanceSheet(end_date=global_end_date),
        start_balance_sheet=BalanceSheet(end_date=global_start_date),
    )

    # Extract metrics from summaries
    def get_summary_value(name: str) -> Decimal:
        return sum(
            (metric.value for metric in cash_statement.summaries if metric.name == name),
            Decimal("0"),
        )

    # Handle case where starting equity account doesn't exist
    try:
        cash_flow_discrepancy = global_cash_statement.get_cash_flow_discrepancy()
    except IndexError:
        cash_flow_discrepancy = None

    return CashFlowMetrics(
        operations_flows=filter_closed_accounts(
            cash_statement.cash_from_operations_balances
        ),
        financing_flows=filter_closed_accounts(
            cash_statement.cash_from_financing_balances
        ),
        investing_flows=filter_closed_accounts(
            cash_statement.cash_from_investing_balances
        ),
        cash_from_operations=get_summary_value("Cash Flow From Operations"),
        cash_from_financing=get_summary_value("Cash Flow From Financing"),
        cash_from_investing=get_summary_value("Cash Flow From Investing"),
        net_cash_flow=get_summary_value("Net Cash Flow"),
        levered_cash_flow=cash_statement.get_levered_after_tax_cash_flow(),
        levered_cash_flow_post_retirement=cash_statement.get_levered_after_tax_after_retirement_cash_flow(),
        cash_flow_discrepancy=cash_flow_discrepancy,
    )
