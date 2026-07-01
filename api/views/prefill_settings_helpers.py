"""
Helper functions for rendering the Prefills Settings section.

Pure functions that take data and return HTML strings via ``render_to_string``.
No database writes and no business logic. Mirrors ``entity_settings_helpers``
plus a nested Doc Search list/form scoped to a prefill.
"""

from typing import List, Optional

from django.template.loader import render_to_string

from api.forms import DocSearchForm, PrefillForm
from api.models import Account, DocSearch, Entity, JournalEntryItem, Prefill
from api.views.form_helpers import resolve_form_values


# --- Prefills (top-level) -----------------------------------------------------


def render_prefills_content(
    prefills: List[Prefill],
    prefill_form_html: str,
    selected_id: Optional[int] = None,
) -> str:
    """Combines the header + table + form into the swappable Prefills fragment."""
    return render_to_string(
        "api/content/prefills-content.html",
        {
            "prefills": prefills,
            "total": len(prefills),
            "selected_id": selected_id,
            "prefill_form": prefill_form_html,
        },
    )


def render_prefill_form(
    prefill: Optional[Prefill] = None,
    change: Optional[str] = None,
    error: Optional[str] = None,
    form: Optional[PrefillForm] = None,
) -> str:
    """Renders the prefill add/edit form HTML. When editing an existing prefill,
    the template lazy-loads that prefill's Doc Searches panel."""
    context = {
        "prefill": prefill,
        "change": change,
        "error": error,
        "form": form,
        "values": resolve_form_values(
            prefill, form, text=("name",), booleans=("is_closed",)
        ),
    }
    return render_to_string("api/entry_forms/prefill-form.html", context)


# --- Doc Searches (nested under a prefill) ------------------------------------


def render_docsearches_content(
    prefill: Prefill,
    docsearches: List[DocSearch],
    docsearch_form_html: str,
    selected_id: Optional[int] = None,
) -> str:
    """Combines the header + table + form into the swappable Doc Searches
    fragment for a single prefill."""
    return render_to_string(
        "api/content/prefill-docsearches-content.html",
        {
            "prefill": prefill,
            "docsearches": docsearches,
            "total": len(docsearches),
            "selected_id": selected_id,
            "docsearch_form": docsearch_form_html,
        },
    )


def render_docsearch_form(
    prefill: Prefill,
    accounts: List[Account],
    entities: List[Entity],
    doc_search: Optional[DocSearch] = None,
    change: Optional[str] = None,
    error: Optional[str] = None,
    form: Optional[DocSearchForm] = None,
) -> str:
    """Renders the Doc Search add/edit form HTML for a prefill."""
    context = {
        "prefill": prefill,
        "accounts": accounts,
        "entities": entities,
        "type_choices": JournalEntryItem.JournalEntryType.choices,
        "selection_choices": DocSearch.STRING_CHOICES,
        "doc_search": doc_search,
        "change": change,
        "error": error,
        "form": form,
        "values": resolve_form_values(
            doc_search,
            form,
            text=(
                "keyword",
                "table_name",
                "row",
                "column",
                "journal_entry_item_type",
                "selection",
            ),
            fks=("account", "entity"),
        ),
    }
    return render_to_string("api/entry_forms/docsearch-form.html", context)
