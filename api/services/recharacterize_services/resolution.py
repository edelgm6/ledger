"""Name/date resolution helpers and the account/entity catalogs.

Deterministic lookups that tolerate the whitespace/case drift the LLM introduces,
plus the guardrail predicate that protects system-managed accounts. Shared by the
evaluation, manual-builder, and LLM layers.
"""

import datetime
from typing import Any, List, Optional, Tuple

from api.models import Account, Entity

from .constants import (
    MUTATING_ACTIONS,
    SWAP_BLOCKED_SPECIAL_TYPES,
    SWAP_BLOCKED_SUB_TYPES,
)


def is_swap_blocked_account(account: Account) -> bool:
    return (
        account.special_type in SWAP_BLOCKED_SPECIAL_TYPES
        or account.sub_type in SWAP_BLOCKED_SUB_TYPES
    )


def _is_mutation(action_kind: Optional[str]) -> bool:
    """True when the action changes the ledger (vs. a view-only inspection)."""
    return action_kind in MUTATING_ACTIONS


def _resolve_named(model, name: Optional[str], label: str):
    """Resolves a catalog name to a row, tolerating the whitespace/case drift the
    LLM introduces even when told to copy names verbatim.

    Tries an exact match first, then falls back to a stripped, case-insensitive
    match so " Federal Taxes Payable" or "federal taxes payable" still resolve.
    The fallback only resolves when it is unambiguous (exactly one match).
    """
    stripped = (name or "").strip()
    if not stripped:
        return None, None
    row = model.objects.filter(name=name).first()
    if row is not None:
        return row, None
    candidates = list(model.objects.filter(name__iexact=stripped)[:2])
    if len(candidates) == 1:
        return candidates[0], None
    return None, f"{label} '{name}' was not found."


def resolve_account(name: Optional[str]) -> Tuple[Optional[Account], Optional[str]]:
    """Resolves an account name to an Account, or returns a blocking error."""
    return _resolve_named(Account, name, "Account")


def resolve_entity(name: Optional[str]) -> Tuple[Optional[Entity], Optional[str]]:
    """Resolves an entity name to an Entity, or returns a blocking error."""
    return _resolve_named(Entity, name, "Entity")


def _as_name_list(value: Any) -> List[str]:
    """Normalizes a filter's account/entity value to a list of names.

    The LLM emits a single name string; the manual form emits a list. Both flow
    through the same evaluation, so a string becomes a one-element list and a
    falsy value becomes an empty list.
    """
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


def _resolve_named_list(model, value: Any, label: str) -> Tuple[List, List[str]]:
    """Resolves every name in a possibly-multi filter value, collecting errors."""
    rows, errors = [], []
    for name in _as_name_list(value):
        row, err = _resolve_named(model, name, label)
        if err:
            errors.append(err)
        elif row is not None:
            rows.append(row)
    return rows, errors


def _parse_date(value: Any) -> Tuple[Optional[datetime.date], Optional[str]]:
    if not value:
        return None, None
    if isinstance(value, datetime.date):
        return value, None
    try:
        return datetime.date.fromisoformat(str(value)), None
    except ValueError:
        return None, f"Could not read the date '{value}'."


def _build_catalogs() -> Tuple[List[str], List[str], List[str]]:
    # Every account is available for entity tagging, so all names go in the
    # usable catalog. The swap-blocked subset is flagged separately so the LLM
    # knows those names may never be the source/target of an account swap.
    accounts = list(Account.objects.all().order_by("name"))
    account_names = [a.name for a in accounts]
    swap_blocked_names = [a.name for a in accounts if is_swap_blocked_account(a)]
    entity_names = list(Entity.objects.order_by("name").values_list("name", flat=True))
    return account_names, entity_names, swap_blocked_names
