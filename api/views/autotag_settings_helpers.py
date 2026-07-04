"""
Helper functions for rendering the Autotags Settings section.

Pure functions that take data and return HTML strings via ``render_to_string``.
No database writes and no business logic. Mirrors ``entity_settings_helpers``.
"""

from typing import List, Optional

from django.template.loader import render_to_string

from api.forms import AutoTagForm
from api.models import Account, AutoTag, Entity, Prefill, Transaction
from api.views.form_helpers import resolve_form_values


def render_autotags_content(
    autotags: List[AutoTag],
    autotag_form_html: str,
    selected_id: Optional[int] = None,
) -> str:
    """Combines the header + table + form into the swappable Autotags fragment."""
    return render_to_string(
        "api/content/autotags-content.html",
        {
            "autotags": autotags,
            "total": len(autotags),
            "selected_id": selected_id,
            "autotag_form": autotag_form_html,
        },
    )


def render_autotag_form(
    accounts: List[Account],
    prefills: List[Prefill],
    entities: List[Entity],
    autotag: Optional[AutoTag] = None,
    change: Optional[str] = None,
    error: Optional[str] = None,
    form: Optional[AutoTagForm] = None,
) -> str:
    """Renders the autotag add/edit form HTML."""
    context = {
        "accounts": accounts,
        "prefills": prefills,
        "entities": entities,
        "type_choices": Transaction.TransactionType.choices,
        "autotag": autotag,
        "change": change,
        "error": error,
        "form": form,
        "values": resolve_form_values(
            autotag,
            form,
            text=("search_string", "transaction_type"),
            fks=("account", "prefill", "entity"),
        ),
    }
    return render_to_string("api/entry_forms/autotag-form.html", context)
