"""Operation evaluation — the single validation choke point.

``_evaluate_operation`` resolves names, enforces every guardrail, and builds the
matched queryset. Preview and apply both call it, so a guardrail can't be bypassed
by either path.
"""

import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from django.db.models import QuerySet

from api.models import Account, Entity, JournalEntryItem

from .constants import (
    ACTION_CHANGE_ACCOUNT,
    ACTION_CLEAR_ENTITY,
    ACTION_SET_ENTITY,
    ACTION_VIEW,
    VALID_ENTRY_TYPES,
)
from .resolution import (
    is_swap_blocked_account,
    resolve_account,
    resolve_entity,
    _parse_date,
    _resolve_named_list,
)


@dataclass
class EvaluatedOperation:
    """The deterministic, validated interpretation of one proposed operation."""

    action_kind: Optional[str] = None
    target_entity: Optional[Entity] = None
    from_account: Optional[Account] = None
    to_account: Optional[Account] = None
    queryset: Optional[QuerySet] = None
    criteria: List[Dict[str, str]] = field(default_factory=list)
    action_summary: str = ""
    errors: List[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return bool(self.errors)


def _filter_criteria(
    description: Optional[str],
    date_from: Optional[datetime.date],
    date_to: Optional[datetime.date],
    accounts: List[Account],
    entities: List[Entity],
    entity_is_empty: bool,
    entry_type: Optional[str],
) -> List[Dict[str, str]]:
    """A labeled, row-by-row breakdown of the filter for the preview panel."""
    rows: List[Dict[str, str]] = []
    if description:
        rows.append({"label": "Description contains", "value": description})
    if date_from:
        rows.append({"label": "Date from", "value": str(date_from)})
    if date_to:
        rows.append({"label": "Date to", "value": str(date_to)})
    if accounts:
        label = "Account" if len(accounts) == 1 else "Account in"
        rows.append({"label": label, "value": ", ".join(a.name for a in accounts)})
    if entities:
        label = "Current entity" if len(entities) == 1 else "Current entity in"
        rows.append({"label": label, "value": ", ".join(e.name for e in entities)})
    if entity_is_empty:
        rows.append({"label": "Current entity", "value": "— none —"})
    if entry_type:
        rows.append({"label": "Type", "value": f"{entry_type}s only"})
    return rows


def _evaluate_operation(operation: Dict[str, Any]) -> EvaluatedOperation:
    """Resolves names, enforces guardrails, and builds the matched queryset.

    Returns an EvaluatedOperation whose ``errors`` list is non-empty when the
    operation is blocked. Used identically by preview and apply.
    """
    result = EvaluatedOperation()
    filter_data = operation.get("filter") or {}
    action_data = operation.get("action") or {}

    # Resolve filter fields. account/entity may be a single name (LLM) or a list
    # of names (manual builder); both normalize to a list here.
    description = filter_data.get("description_contains") or None
    filter_accounts, errs = _resolve_named_list(
        Account, filter_data.get("account"), "Account"
    )
    result.errors.extend(errs)
    filter_entities, errs = _resolve_named_list(
        Entity, filter_data.get("entity"), "Entity"
    )
    result.errors.extend(errs)
    date_from, err = _parse_date(filter_data.get("date_from"))
    if err:
        result.errors.append(err)
    date_to, err = _parse_date(filter_data.get("date_to"))
    if err:
        result.errors.append(err)

    entity_is_empty = bool(filter_data.get("entity_is_empty"))

    entry_type = filter_data.get("entry_type") or None
    if entry_type is not None:
        entry_type = str(entry_type).lower()
        if entry_type not in VALID_ENTRY_TYPES:
            entry_type = None

    result.criteria = _filter_criteria(
        description,
        date_from,
        date_to,
        filter_accounts,
        filter_entities,
        entity_is_empty,
        entry_type,
    )

    # Guard against a filter that would match everything.
    has_any_filter = any(
        [
            description,
            date_from,
            date_to,
            filter_accounts,
            filter_entities,
            entity_is_empty,
            entry_type,
        ]
    )
    if not has_any_filter:
        result.errors.append(
            "This operation has no criteria; it would match every item. "
            "Add at least one filter (description, dates, account, entity, or type)."
        )

    # Resolve and validate the action.
    result.action_kind = action_data.get("type")
    if result.action_kind == ACTION_SET_ENTITY:
        target_entity, err = resolve_entity(action_data.get("entity"))
        if err:
            result.errors.append(err)
        elif target_entity is None:
            result.errors.append("Set-entity requires an entity name.")
        result.target_entity = target_entity
        result.action_summary = (
            f"set entity to \"{target_entity.name}\"" if target_entity else "set entity"
        )
    elif result.action_kind == ACTION_CLEAR_ENTITY:
        result.action_summary = "clear the entity"
    elif result.action_kind == ACTION_VIEW:
        # View-only: no entity/account to resolve and nothing to mutate. The
        # filter guard above still requires at least one criterion.
        result.action_summary = "view matching items (no changes)"
    elif result.action_kind == ACTION_CHANGE_ACCOUNT:
        # A swap maps one source account to one destination (their type/sub-type
        # must match), so the filter must pin down exactly one source account.
        filter_account = filter_accounts[0] if len(filter_accounts) == 1 else None
        if not filter_accounts:
            result.errors.append(
                "Changing an account requires a source account in the filter."
            )
        elif filter_account is None:  # more than one source matched the filter
            result.errors.append(
                "Changing an account requires exactly one source account in the "
                "filter, not several."
            )
        result.from_account = filter_account
        to_account, err = resolve_account(action_data.get("to_account"))
        if err:
            result.errors.append(err)
        elif to_account is None:
            result.errors.append("Changing an account requires a destination account.")
        result.to_account = to_account
        result.action_summary = (
            f"change account from \"{filter_account.name}\" to \"{to_account.name}\""
            if filter_account and to_account
            else "change account"
        )
        # Account-swap guardrails.
        if filter_account and to_account:
            if filter_account == to_account:
                result.errors.append("The FROM and TO accounts are the same.")
            if is_swap_blocked_account(filter_account):
                result.errors.append(
                    f"\"{filter_account.name}\" is a system-managed account and "
                    "cannot be the source of an account swap."
                )
            if is_swap_blocked_account(to_account):
                result.errors.append(
                    f"\"{to_account.name}\" is a system-managed account and cannot "
                    "be the destination of an account swap."
                )
            if (
                filter_account.type != to_account.type
                or filter_account.sub_type != to_account.sub_type
            ):
                result.errors.append(
                    f"\"{filter_account.name}\" ({filter_account.get_type_display()}/"
                    f"{filter_account.get_sub_type_display()}) and "
                    f"\"{to_account.name}\" ({to_account.get_type_display()}/"
                    f"{to_account.get_sub_type_display()}) have different "
                    "type/sub-type, so the swap would change the statements."
                )
    else:
        result.errors.append(f"Unknown action '{result.action_kind}'.")

    if result.errors:
        return result

    # Build the matched queryset.
    queryset = JournalEntryItem.objects.filter_for_recharacterize(
        description=description,
        date_from=date_from,
        date_to=date_to,
        accounts=filter_accounts,
        entities=filter_entities,
        entity_is_empty=entity_is_empty,
        entry_type=entry_type,
    )

    result.queryset = queryset
    return result
