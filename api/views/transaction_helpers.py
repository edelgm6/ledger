"""
Helper functions for rendering transaction HTML.

These pure functions provide testable, reusable rendering
that takes data and returns HTML strings.
"""

from typing import List, Optional

from django.template.loader import render_to_string

from api import utils
from api.forms import TransactionFilterForm, TransactionForm, TransactionLinkForm
from api.models import Transaction


def render_transaction_table(
    transactions: List[Transaction],
    index: int = 0,
    no_highlight: bool = False,
    row_url: Optional[str] = None,
    double_row_click: bool = False,
) -> str:
    """
    Renders the transaction table HTML.

    Args:
        transactions: List of transactions to display
        index: Index of transaction to highlight (default 0)
        no_highlight: If True, don't highlight any row
        row_url: URL pattern for row clicks
        double_row_click: If True, require double-click to activate

    Returns:
        HTML string for transaction table
    """
    context = {
        "transactions": transactions,
        "index": index,
        "no_highlight": no_highlight,
        "row_url": row_url,
        "double_row_click": double_row_click,
    }

    table_template = "api/tables/transactions-table-new.html"
    return render_to_string(table_template, context)


def render_transaction_form(
    transaction: Optional[Transaction] = None,
    created_transaction: Optional[Transaction] = None,
    change: Optional[str] = None,
) -> str:
    """
    Renders the transaction form HTML.

    Args:
        transaction: Existing transaction to edit (if updating)
        created_transaction: Transaction that was just created/updated/deleted
        change: Type of change ("create", "update", "delete")

    Returns:
        HTML string for transaction form
    """
    form_template = "api/entry_forms/transaction-form.html"

    if transaction:
        form = TransactionForm(instance=transaction)
    else:
        form = TransactionForm()

    context = {
        "form": form,
        "transaction": transaction,
        "created_transaction": created_transaction,
        "change": change,
    }

    return render_to_string(form_template, context)


def render_transaction_filter_form(
    is_closed: Optional[bool] = None,
    has_linked_transaction: Optional[bool] = None,
    transaction_type: Optional[List[str]] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    get_url: Optional[str] = None,
) -> str:
    """
    Renders the transaction filter form HTML.

    Args:
        is_closed: Initial value for closed filter
        has_linked_transaction: Initial value for linked filter
        transaction_type: Initial value for type filter
        date_from: Initial value for start date (as string)
        date_to: Initial value for end date (as string)
        get_url: URL for form submission

    Returns:
        HTML string for filter form
    """
    filter_form_template = "api/filter_forms/transactions-filter-form.html"

    form = TransactionFilterForm(prefix="filter")
    form.initial["is_closed"] = is_closed
    form.initial["has_linked_transaction"] = has_linked_transaction
    form.initial["transaction_type"] = transaction_type
    form.initial["date_from"] = date_from
    form.initial["date_to"] = date_to

    context = {
        "filter_form": form,
        "get_url": get_url,
    }

    return render_to_string(filter_form_template, context)


def render_transaction_link_form() -> str:
    """
    Renders the transaction link form HTML.

    Returns:
        HTML string for link form
    """
    entry_form_template = "api/entry_forms/transaction-link-form.html"
    return render_to_string(
        entry_form_template,
        {"link_form": TransactionLinkForm()}
    )


def render_transactions_content(
    table_html: str,
    form_html: str,
    transaction: Optional[Transaction] = None,
) -> str:
    """
    Renders the full transactions content (table + form).

    Args:
        table_html: Pre-rendered table HTML
        form_html: Pre-rendered form HTML
        transaction: Optional transaction for context

    Returns:
        HTML string for complete content area
    """
    content_template = "api/content/transactions-content.html"
    context = {
        "transactions_form": form_html,
        "table": table_html,
        "transaction": transaction,
    }
    return render_to_string(content_template, context)


def render_transactions_link_content(
    table_html: str,
    link_form_html: str,
) -> str:
    """
    Renders the transactions linking content (table + link form).

    Args:
        table_html: Pre-rendered table HTML
        link_form_html: Pre-rendered link form HTML

    Returns:
        HTML string for linking content area
    """
    content_template = "api/content/transactions-link-content.html"
    context = {
        "table": table_html,
        "link_form": link_form_html,
    }
    return render_to_string(content_template, context)


def format_date_for_form(date) -> Optional[str]:
    """
    Formats a date object for use in form initial data.

    Args:
        date: Date object or None

    Returns:
        Formatted date string or None
    """
    return utils.format_datetime_to_string(date) if date else None
