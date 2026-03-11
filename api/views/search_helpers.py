"""
Helper functions for rendering search HTML.

These pure functions provide testable, reusable rendering
that takes data and returns HTML strings.
"""

from typing import List, Optional

from django.template.loader import render_to_string

from api.forms import SearchFilterForm
from api.models import Account, JournalEntryItem, Transaction


def render_search_filter_form(get_url: str) -> str:
    """Renders the search filter form HTML."""
    form = SearchFilterForm()
    return render_to_string(
        "api/filter_forms/search-filter-form.html",
        {"form": form, "get_url": get_url},
    )


def render_search_results_table(
    transactions: List[Transaction],
    count: int,
) -> str:
    """Renders the search results table HTML with JEI details."""
    # Build per-transaction JEI data without mutating model instances
    transactions_data = []
    for txn in transactions:
        je = getattr(txn, "journal_entry", None)
        if je:
            debit_items = []
            credit_items = []
            entity_names = set()
            for i in je.journal_entry_items.all():
                if i.type == JournalEntryItem.JournalEntryType.DEBIT:
                    debit_items.append(i)
                else:
                    credit_items.append(i)
                if i.entity:
                    entity_names.add(i.entity.name)
            entity_names = sorted(entity_names)
        else:
            debit_items = []
            credit_items = []
            entity_names = []

        transactions_data.append({
            "transaction": txn,
            "debit_items": debit_items,
            "credit_items": credit_items,
            "entity_names": entity_names,
        })

    return render_to_string(
        "api/tables/search-results-table.html",
        {"transactions_data": transactions_data, "count": count},
    )


def render_bulk_action_form(accounts: List[Account]) -> str:
    """Renders the FROM/TO account dropdowns for bulk update."""
    return render_to_string(
        "api/entry_forms/bulk-account-change-form.html",
        {"accounts": accounts},
    )


def render_bulk_preview(
    affected_count: int,
    from_account: Account,
    to_account: Account,
) -> str:
    """Renders the bulk update preview/confirmation message."""
    return render_to_string(
        "api/components/bulk-preview.html",
        {
            "affected_count": affected_count,
            "from_account": from_account,
            "to_account": to_account,
        },
    )


def render_search_content(
    table_html: str,
    bulk_form_html: Optional[str] = None,
    success_message: Optional[str] = None,
) -> str:
    """Renders the full search content area (table + bulk form)."""
    return render_to_string(
        "api/content/search-content.html",
        {
            "table": table_html,
            "bulk_form": bulk_form_html,
            "success_message": success_message,
        },
    )
