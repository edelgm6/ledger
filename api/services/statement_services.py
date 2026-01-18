"""
Service functions for statement generation and processing.

Contains business logic for filtering accounts, building statement summaries,
finding unbalanced entries, and calculating metrics. All database writes
go through services with atomic transactions.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db.models import Case, DecimalField, F, Sum, When

from api.models import Account, JournalEntry, JournalEntryItem
from api.statement import Balance, BalanceSheet, CashFlowStatement, IncomeStatement


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

        for sub_type in Account.SUBTYPE_TO_TYPE_MAP[account_type]:
            # Filter balances for this sub_type
            balances = [
                balance
                for balance in statement.balances
                if balance.account.sub_type == sub_type
            ]

            # Calculate sub_type total
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
    journal_entry_items = list(
        JournalEntryItem.objects.filter(
            account__pk=account_id,
            journal_entry__date__gte=from_date,
            journal_entry__date__lte=to_date,
            amount__gt=0,
        )
        .select_related("journal_entry__transaction", "account")
        .order_by("journal_entry__date")
    )

    # Apply signing logic
    for entry in journal_entry_items:
        entry.amount_signed = entry.amount

        # INCOME debits are negative (reduces income)
        if (
            entry.account.type == Account.Type.INCOME
            and entry.type == JournalEntryItem.JournalEntryType.DEBIT
        ):
            entry.amount_signed *= -1

        # EXPENSE credits are negative (reduces expense)
        if (
            entry.account.type == Account.Type.EXPENSE
            and entry.type == JournalEntryItem.JournalEntryType.CREDIT
        ):
            entry.amount_signed *= -1

    # Get the account
    account = None
    if journal_entry_items:
        account = journal_entry_items[0].account

    return StatementDetailData(
        journal_entry_items=journal_entry_items,
        account=account,
    )


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
