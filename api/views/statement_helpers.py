"""
Helper functions for statement rendering.

All functions are pure: data → HTML string.
No database writes, no business logic.
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional

from django.template.loader import render_to_string
from django.urls import reverse

from api import utils
from api.forms import FromToDateForm
from api.models import JournalEntry
from api.services.statement_services import (
    CashFlowMetrics,
    StatementDetailData,
    StatementSummary,
)


def format_date_for_form(date_obj: Optional[date]) -> str:
    """
    Format a date for use in a form field.

    Args:
        date_obj: Date to format, or None

    Returns:
        Formatted date string (YYYY-MM-DD) or default value if None
    """
    if date_obj is None:
        return "2023-01-01"  # Default for balance sheet (no from_date)
    return utils.format_datetime_to_string(date_obj)


def render_statement_filter_form(
    statement_type: str,
    from_date: Optional[date],
    to_date: date,
) -> str:
    """
    Render the date filter form for statements.

    Args:
        statement_type: Type of statement ("income", "balance", "cash")
        from_date: Start date (None for balance sheet)
        to_date: End date

    Returns:
        HTML string for the filter form
    """
    initial_data = {
        "date_from": format_date_for_form(from_date),
        "date_to": utils.format_datetime_to_string(to_date),
    }

    context = {
        "filter_form": FromToDateForm(initial=initial_data),
        "get_url": reverse("statements", args=(statement_type,)),
        "statement_type": statement_type,
    }

    return render_to_string("api/filter_forms/from-to-date-form.html", context)


def render_income_statement(
    summary: StatementSummary,
    tax_rate: Optional[float],
    savings_rate: Optional[float],
    from_date: date,
    to_date: date,
) -> str:
    """
    Render the income statement HTML.

    Args:
        summary: StatementSummary with account type/sub_type hierarchy
        tax_rate: Effective tax rate (or None)
        savings_rate: Savings rate (or None)
        from_date: Start date
        to_date: End date

    Returns:
        HTML string for income statement
    """
    # Convert StatementSummary to dict format expected by template
    summary_dict = _convert_summary_to_dict(summary)

    context = {
        "summary": summary_dict,
        "tax_rate": tax_rate if tax_rate is not None else 0,
        "savings_rate": savings_rate if savings_rate is not None else 0,
        "from_date": from_date,
        "to_date": to_date,
    }

    return render_to_string("api/content/income-content.html", context)


def render_balance_sheet(
    summary: StatementSummary,
    cash_percent_assets: Optional[float],
    debt_to_equity_ratio: Optional[float],
    liquid_percent_assets: Optional[float],
    unbalanced_entries: List[JournalEntry],
) -> str:
    """
    Render the balance sheet HTML.

    Args:
        summary: StatementSummary with account type/sub_type hierarchy
        cash_percent_assets: Cash as % of assets
        debt_to_equity_ratio: Debt to equity ratio
        liquid_percent_assets: Liquid assets as % of total
        unbalanced_entries: List of unbalanced journal entries (for warning)

    Returns:
        HTML string for balance sheet
    """
    # Convert StatementSummary to dict format expected by template
    summary_dict = _convert_summary_to_dict(summary)

    context = {
        "summary": summary_dict,
        "cash_percent_assets": cash_percent_assets,
        "debt_to_equity_ratio": debt_to_equity_ratio,
        "liquid_percent_assets": liquid_percent_assets,
        "unbalanced_entries": unbalanced_entries,
    }

    return render_to_string("api/content/balance-sheet-content.html", context)


def render_cash_flow_statement(metrics: CashFlowMetrics) -> str:
    """
    Render the cash flow statement HTML.

    Args:
        metrics: CashFlowMetrics with all calculated values

    Returns:
        HTML string for cash flow statement
    """
    context = {
        "operations_flows": metrics.operations_flows,
        "financing_flows": metrics.financing_flows,
        "investing_flows": metrics.investing_flows,
        "cash_from_operations": metrics.cash_from_operations,
        "cash_from_financing": metrics.cash_from_financing,
        "cash_from_investing": metrics.cash_from_investing,
        "net_cash_flow": metrics.net_cash_flow,
        "levered_cash_flow": metrics.levered_cash_flow,
        "levered_cash_flow_post_retirement": metrics.levered_cash_flow_post_retirement,
        "cash_flow_discrepancy": metrics.cash_flow_discrepancy,
    }

    return render_to_string("api/content/cash-flow-content.html", context)


def render_statement_detail_table(detail_data: StatementDetailData) -> str:
    """
    Render the statement detail table for account drill-down.

    Args:
        detail_data: StatementDetailData with signed journal entry items

    Returns:
        HTML string for detail table
    """
    context = {
        "journal_entry_items": detail_data.journal_entry_items,
    }

    return render_to_string("api/tables/statement-detail-table.html", context)


def _convert_summary_to_dict(summary: StatementSummary) -> dict:
    """
    Convert StatementSummary dataclass to dict format expected by templates.

    Internal helper function.

    Args:
        summary: StatementSummary dataclass

    Returns:
        Dict matching the template's expected structure
    """
    result = {}
    for account_type, type_summary in summary.account_types.items():
        result[account_type] = {
            "name": type_summary.name,
            "total": type_summary.total,
            "balances": [
                {
                    "name": sub.name,
                    "balances": sub.balances,
                    "total": sub.total,
                }
                for sub in type_summary.sub_types
            ],
        }
    return result
