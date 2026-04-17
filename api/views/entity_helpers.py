"""
Helper functions for rendering entity-related HTML.

These pure functions handle HTML rendering, extracting
rendering logic into testable, reusable functions.
"""

from typing import List, Optional

from django.template.loader import render_to_string

from api.forms import JournalEntryItemEntityForm
from api.models import Entity, JournalEntryItem
from api.services.entity_services import (
    EntityHistoryData,
    GroupedEntityBalances,
)


def render_untagged_entries_table(items: List[JournalEntryItem]) -> Optional[str]:
    """
    Renders the untagged journal entries table HTML.

    Returns None if there are no items to display.
    """
    if not items:
        return None

    return render_to_string(
        "api/tables/payables-receivables-table.html",
        {"payables_receivables": items},
    )


def render_entity_grouped_balances_table(
    grouped_balances: List[GroupedEntityBalances],
    hide_zero: bool,
    history_html: str,
) -> str:
    """
    Renders the grouped entity balances table with history panel.

    Args:
        grouped_balances: List of GroupedEntityBalances (one per account)
        hide_zero: Whether $0-balance entities are currently hidden
        history_html: Pre-rendered history table HTML
    """
    return render_to_string(
        "api/tables/entity-balances-grouped.html",
        {
            "grouped_balances": grouped_balances,
            "hide_zero": hide_zero,
            "entity_history_table": history_html,
        },
    )


def render_entity_history_table(history_data: EntityHistoryData) -> str:
    """
    Renders the entity history table HTML.

    Returns empty string if no items to display.
    """
    if not history_data.items:
        return ""

    journal_entry_items = []
    for history_item in history_data.items:
        item = history_item.journal_entry_item
        item.balance = history_item.running_balance
        journal_entry_items.append(item)

    final_balance = history_data.items[-1].running_balance

    return render_to_string(
        "api/tables/entity-history-table.html",
        {
            "journal_entry_items": journal_entry_items,
            "entity_name": history_data.entity_name,
            "account_name": history_data.account_name,
            "final_balance": final_balance,
        },
    )


def render_entity_tag_form(
    journal_entry_item: JournalEntryItem,
    preloaded_entity: Optional[Entity] = None,
) -> str:
    """
    Renders the entity tagging form HTML.

    Args:
        journal_entry_item: The item to be tagged
        preloaded_entity: Entity to pre-select in the dropdown
    """
    initial_data = {"entity": preloaded_entity} if preloaded_entity else {}
    form = JournalEntryItemEntityForm(
        instance=journal_entry_item, initial=initial_data
    )

    return render_to_string(
        "api/entry_forms/entity-tag-form.html",
        {
            "form": form,
            "journal_entry_item_id": journal_entry_item.pk,
        },
    )


def render_entity_page(
    table_html: Optional[str],
    form_html: Optional[str],
    balances_table_html: str,
    is_initial_load: bool,
) -> str:
    """
    Renders the full entity/payables-receivables page HTML.

    Args:
        table_html: Rendered untagged entries table (or None)
        form_html: Rendered entity tag form (or None)
        balances_table_html: Rendered entity balances table
        is_initial_load: Whether this is the initial page load (shows header)
    """
    return render_to_string(
        "api/views/payables-receivables.html",
        {
            "table": table_html,
            "form": form_html,
            "is_initial_load": is_initial_load,
            "balances_table": balances_table_html,
        },
    )
