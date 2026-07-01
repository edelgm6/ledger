"""
Service layer for Prefill and Doc Search config CRUD (Settings page).

A Prefill is a reusable template. Its Doc Searches tell the paystub/document
parser where to find each value on a document and which account/metadata field
it maps to. This module exposes the list/create/update/delete operations the
Settings UI needs, delegating writes to the shared ``crud`` helpers.

Mirrors ``entity_services`` (single-model config CRUD) plus a nested child
(Doc Search) scoped to its parent prefill, following ``loan_services``.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from django.db.models import Count

from api.models import Account, DocSearch, Entity, Prefill
from api.services import crud


@dataclass
class PrefillResult:
    """Result of a prefill create/update/delete operation."""
    success: bool
    prefill: Optional[Prefill] = None
    error: Optional[str] = None


@dataclass
class DocSearchResult:
    """Result of a doc search create/update/delete operation."""
    success: bool
    doc_search: Optional[DocSearch] = None
    error: Optional[str] = None


# --- Prefill CRUD -------------------------------------------------------------


def get_prefills() -> List[Prefill]:
    """Returns all prefills (open first, then alphabetical) annotated with
    ``docsearch_count`` — the number of Doc Searches attached to each."""
    return list(
        Prefill.objects.annotate(
            docsearch_count=Count("docsearch"),
        ).order_by("is_closed", "name")
    )


PREFILL_FIELDS = ("name", "is_closed")


def save_prefill(
    cleaned_data: Dict[str, Any], instance: Optional[Prefill] = None
) -> PrefillResult:
    """Creates or updates a prefill from validated form data. ``instance`` is
    the prefill being edited (None to create)."""
    prefill, error = crud.save_model(
        Prefill, PREFILL_FIELDS, cleaned_data, instance
    )
    return PrefillResult(success=error is None, prefill=prefill, error=error)


def delete_prefill(prefill_id: int) -> PrefillResult:
    """Deletes a prefill, gracefully blocking when it is still referenced.

    Prefills are PROTECT-referenced by Doc Searches, S3 files, and transactions,
    so rather than 500ing on a ProtectedError we return a friendly message the
    UI can display inline and suggest closing instead.
    """
    prefill, error = crud.delete_model(
        Prefill,
        prefill_id,
        not_found="Prefill not found.",
        protected=lambda p: (
            f"Can't delete '{p.name}' — it's still used by other records "
            "(doc searches, uploaded documents, or transactions). "
            "Close it instead to archive it."
        ),
    )
    return PrefillResult(success=error is None, prefill=prefill, error=error)


# --- Doc Search CRUD (scoped to a prefill) ------------------------------------


def get_docsearches(prefill_id: int) -> List[DocSearch]:
    """Returns the Doc Searches for a prefill, ordered by pk."""
    return list(
        DocSearch.objects.filter(prefill_id=prefill_id)
        .select_related("account", "entity")
        .order_by("pk")
    )


def get_docsearch_form_options() -> Tuple[List[Account], List[Entity]]:
    """Returns the DB-backed dropdown options for the Doc Search form: open
    accounts and all entities. Static choice lists (type, selection) live in the
    helper, matching ``get_bill_rule_form_options``."""
    accounts = list(Account.objects.filter(is_closed=False).order_by("name"))
    entities = list(Entity.objects.all().order_by("name"))
    return accounts, entities


DOC_SEARCH_FIELDS = (
    "keyword",
    "table_name",
    "row",
    "column",
    "account",
    "journal_entry_item_type",
    "selection",
    "entity",
)


def save_docsearch(
    prefill: Prefill,
    cleaned_data: Dict[str, Any],
    instance: Optional[DocSearch] = None,
) -> DocSearchResult:
    """Creates or updates a Doc Search under ``prefill``. New rows get the
    parent FK before the fields are copied over."""
    instance = instance or DocSearch(prefill=prefill)
    doc_search, error = crud.save_model(
        DocSearch, DOC_SEARCH_FIELDS, cleaned_data, instance
    )
    return DocSearchResult(
        success=error is None, doc_search=doc_search, error=error
    )


def delete_docsearch(docsearch_id: int) -> DocSearchResult:
    """Deletes a Doc Search by pk."""
    doc_search, error = crud.delete_model(
        DocSearch,
        docsearch_id,
        not_found="Doc search not found.",
        protected="Can't delete this doc search — it's still referenced.",
    )
    return DocSearchResult(
        success=error is None, doc_search=doc_search, error=error
    )
