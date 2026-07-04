"""
Service layer for AutoTag config CRUD (Settings page).

An AutoTag is a rule: when its ``search_string`` appears (case-insensitively) in
an incoming transaction's description, the transaction is pre-filled with the
tag's account/entity/prefill and transaction type (see
``Transaction.apply_autotags``). This module exposes the list/create/update/
delete operations the Settings UI needs, delegating writes to the shared
``crud`` helpers.

Mirrors ``entity_services`` (single-model config CRUD).
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from api.models import Account, AutoTag, Entity, Prefill
from api.services import crud


@dataclass
class AutoTagResult:
    """Result of an autotag create/update/delete operation."""
    success: bool
    autotag: Optional[AutoTag] = None
    error: Optional[str] = None


def get_autotags() -> List[AutoTag]:
    """Returns all autotags ordered by search string, with the account
    pre-fetched for the list display (the only relation the list renders)."""
    return list(
        AutoTag.objects.select_related("account").order_by("search_string")
    )


def get_autotag_form_options() -> Tuple[List[Account], List[Prefill], List[Entity]]:
    """Returns the DB-backed dropdown options for the AutoTag form: open
    accounts, open prefills, and all entities. The static transaction-type
    choices live on ``Transaction.TransactionType`` and are supplied by the
    helper, matching ``get_docsearch_form_options``."""
    accounts = list(Account.objects.filter(is_closed=False).order_by("name"))
    prefills = list(Prefill.objects.filter(is_closed=False).order_by("name"))
    entities = list(Entity.objects.all().order_by("name"))
    return accounts, prefills, entities


AUTOTAG_FIELDS = (
    "search_string",
    "account",
    "transaction_type",
    "prefill",
    "entity",
)


def save_autotag(
    cleaned_data: Dict[str, Any], instance: Optional[AutoTag] = None
) -> AutoTagResult:
    """Creates or updates an autotag from validated form data. ``instance`` is
    the autotag being edited (None to create)."""
    autotag, error = crud.save_model(
        AutoTag, AUTOTAG_FIELDS, cleaned_data, instance
    )
    return AutoTagResult(success=error is None, autotag=autotag, error=error)


def delete_autotag(autotag_id: int) -> AutoTagResult:
    """Deletes an autotag by pk.

    Nothing references AutoTag and its own FKs are CASCADE, so a ProtectedError
    isn't expected; the shared helper still handles it for parity.
    """
    autotag, error = crud.delete_model(
        AutoTag,
        autotag_id,
        not_found="Auto tag not found.",
        protected="Can't delete this auto tag — it's still referenced.",
    )
    return AutoTagResult(success=error is None, autotag=autotag, error=error)
