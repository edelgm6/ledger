"""The manual operation builder.

Turns manual-form input into a ``{filter, action}`` operation dict that flows
through preview/apply/revert unchanged.
"""

from dataclasses import dataclass
from typing import Any, Dict, List

from api.models import Account, Entity

from .constants import ACTION_CHANGE_ACCOUNT, ACTION_SET_ENTITY, ACTION_VIEW
from .resolution import _as_name_list, _build_catalogs


# --- Manual operation builder ----------------------------------------------
#
# The manual builder lets a user construct a {filter, action} operation by hand.
# The dict it produces flows through preview_plan / apply_operation /
# revert_change unchanged, so all guardrails apply.


@dataclass
class FormCatalogs:
    """Name lists for populating the manual builder's <select> inputs."""

    accounts: List[str]
    entities: List[str]


def manual_form_catalogs() -> FormCatalogs:
    """Account/entity names for the manual builder's <select> inputs."""
    account_names, entity_names = _build_catalogs()
    return FormCatalogs(accounts=account_names, entities=entity_names)


def build_manual_operation(data: Dict[str, Any]) -> Dict[str, Any]:
    """Builds a ``{filter, action}`` operation dict from cleaned form data.

    Empty fields are dropped so the no-filter guard and action_summary logic have
    a clean dict to work with, and dates are stored as ISO strings to keep the
    session plan JSON-serializable. All semantic validation (swap-blocked
    accounts, type match, empty filter) is deferred to _evaluate_operation, which
    surfaces a blocked op in the preview.
    """
    filter_data: Dict[str, Any] = {}
    if data.get("description_contains"):
        filter_data["description_contains"] = data["description_contains"]
    if data.get("date_from"):
        filter_data["date_from"] = data["date_from"].isoformat()
    if data.get("date_to"):
        filter_data["date_to"] = data["date_to"].isoformat()
    # account/entity arrive as Account/Entity objects (multi-select); store the
    # names so the plan stays JSON-serializable (the by-name shape apply consumes).
    accounts = list(data.get("account") or [])
    if accounts:
        filter_data["account"] = [a.name for a in accounts]
    entities = list(data.get("entity") or [])
    if entities:
        filter_data["entity"] = [e.name for e in entities]
    if data.get("entity_is_empty"):
        filter_data["entity_is_empty"] = True
    if data.get("entry_type"):
        filter_data["entry_type"] = data["entry_type"]

    action_kind = data.get("action_type")
    action_data: Dict[str, Any] = {"type": action_kind}
    if action_kind == ACTION_SET_ENTITY:
        action_data["entity"] = data.get("target_entity") or ""
    elif action_kind == ACTION_CHANGE_ACCOUNT:
        action_data["to_account"] = data.get("to_account") or ""

    return {"filter": filter_data, "action": action_data}


def _name_pks(model, value: Any) -> List[str]:
    """Resolves a filter's account/entity names to a list of string PKs.

    The manual form's multi-selects mark an option selected via
    ``option.pk|stringformat:"s" in field.value`` (see typeahead-multiselect.html),
    so an unbound form's ``initial`` must carry string PKs — not instances or ints
    — for prefilled values to render as selected. Names that no longer resolve are
    dropped (the user re-picks them).
    """
    names = _as_name_list(value)
    if not names:
        return []
    pks = model.objects.filter(name__in=names).values_list("pk", flat=True)
    return [str(pk) for pk in pks]


def operation_to_form_initial(operation: Dict[str, Any]) -> Dict[str, Any]:
    """Reverse of ``build_manual_operation``: an ``initial`` dict for the manual
    form, used to prefill the builder when editing an existing operation.

    Dates stay ISO strings (an ``<input type=date>`` renders them as-is); account
    and entity become string-PK lists for the multi-selects; the action and its
    single-valued target/destination names pass straight through.
    """
    filter_data = operation.get("filter") or {}
    action_data = operation.get("action") or {}

    return {
        "description_contains": filter_data.get("description_contains") or "",
        "date_from": filter_data.get("date_from") or "",
        "date_to": filter_data.get("date_to") or "",
        "account": _name_pks(Account, filter_data.get("account")),
        "entity": _name_pks(Entity, filter_data.get("entity")),
        "entity_is_empty": bool(filter_data.get("entity_is_empty")),
        "entry_type": filter_data.get("entry_type") or "",
        "action_type": action_data.get("type") or ACTION_VIEW,
        "target_entity": action_data.get("entity") or "",
        "to_account": action_data.get("to_account") or "",
    }
