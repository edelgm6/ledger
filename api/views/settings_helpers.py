"""
Helper functions for rendering Settings page HTML.

These pure functions take data and return HTML strings via render_to_string.
They contain no database writes and no business logic.
"""

from typing import Any, Dict, List, Optional

from django.db.models import QuerySet
from django.template.loader import render_to_string

from api.forms import AccountForm
from api.models import Account


def build_subtype_map() -> Dict[str, List[Dict[str, str]]]:
    """Builds a {type_value: [{value, label}, ...]} map of valid sub-types per
    account type, for the client-side Type -> Sub-type dependent select.

    Reads only the model constant (no DB), so it stays a pure helper.
    """
    subtype_map: Dict[str, List[Dict[str, str]]] = {}
    for type_value, _label in Account.Type.choices:
        subtypes = Account.SUBTYPE_TO_TYPE_MAP.get(type_value, [])
        subtype_map[type_value] = [
            {"value": st.value, "label": str(st.label)} for st in subtypes
        ]
    return subtype_map


def render_settings_content(
    accounts: List[Account],
    account_form_html: str,
    selected_id: Optional[int] = None,
) -> str:
    """Combines the header + table + form into the swappable right-pane fragment."""
    return render_to_string(
        "api/content/settings-content.html",
        {
            "accounts": accounts,
            "total": len(accounts),
            "selected_id": selected_id,
            "account_form": account_form_html,
        },
    )


def _form_values(
    account: Optional[Account], form: Optional[AccountForm]
) -> Dict[str, Any]:
    """Resolves the current field values to display: submitted data on a bound
    (invalid) form, else the account being edited, else blank-create defaults."""
    if form is not None and form.is_bound:
        data = form.data
        return {
            "name": data.get("name", ""),
            "type": data.get("type", "asset"),
            "sub_type": data.get("sub_type", ""),
            "entity": data.get("entity", ""),
            "csv_profile": data.get("csv_profile", ""),
            "is_closed": "is_closed" in data,
            "is_depreciation": "is_depreciation" in data,
        }
    if account is not None:
        return {
            "name": account.name,
            "type": account.type,
            "sub_type": account.sub_type,
            "entity": str(account.entity_id or ""),
            "csv_profile": str(account.csv_profile_id or ""),
            "is_closed": account.is_closed,
            "is_depreciation": account.is_depreciation,
        }
    return {
        "name": "",
        "type": Account.Type.ASSET,
        "sub_type": "",
        "entity": "",
        "csv_profile": "",
        "is_closed": False,
        "is_depreciation": False,
    }


def render_account_form(
    entities: QuerySet,
    csv_profiles: QuerySet,
    account: Optional[Account] = None,
    change: Optional[str] = None,
    error: Optional[str] = None,
    form: Optional[AccountForm] = None,
) -> str:
    """Renders the account add/edit form HTML.

    Args:
        entities: Entity queryset for the Entity dropdown.
        csv_profiles: CSVProfile queryset for the CSV Profile dropdown.
        account: Existing account being edited (None for the create form).
        change: Type of change just performed ("create"/"update"/"delete").
        error: A friendly error message to display inline (e.g. delete blocked).
        form: A bound form carrying validation errors to redisplay.
    """
    context = {
        "account": account,
        "change": change,
        "error": error,
        "form": form,
        "values": _form_values(account, form),
        "type_choices": Account.Type.choices,
        "subtype_map": build_subtype_map(),
        "entities": entities,
        "csv_profiles": csv_profiles,
    }
    return render_to_string("api/entry_forms/account-form.html", context)
