"""
Service layer for the agentic bulk-recharacterization tool.

A user describes, in plain language, which journal entry items to target and
what change to make. The LLM (see gemini_services) only proposes a structured
plan — a list of ``{filter, action}`` operations. Everything in this module is
deterministic: it resolves names, enforces guardrails that protect book
integrity, previews the exact effect, and applies it atomically.

The only mutations allowed are setting/clearing an item's entity and swapping
one account for another. Amounts and debit/credit type are never touched, so the
per-journal-entry balance is structurally preserved.
"""

import datetime
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from django.core.paginator import Paginator
from django.db import transaction as db_transaction
from django.db.models import QuerySet
from django.utils import timezone

from api.models import (
    Account,
    Entity,
    JournalEntryItem,
    RecharacterizeChange,
    RecharacterizeChangeItem,
)
from api.services import gemini_services

logger = logging.getLogger(__name__)


# Starting-equity, retained-earnings, and unrealized-gains accounts are derived
# by statement and reconciliation logic (see api/statement.py cash-flow logic
# and Reconciliation.plug_investment_change), so their balances must never be
# moved by an account swap. Their items may still be re-tagged with an entity —
# entity tagging never touches a balance — so this set blocks account swaps only.
SWAP_BLOCKED_SPECIAL_TYPES = [
    Account.SpecialType.UNREALIZED_GAINS_AND_LOSSES,
    Account.SpecialType.STARTING_EQUITY,
]
SWAP_BLOCKED_SUB_TYPES = [
    Account.SubType.RETAINED_EARNINGS,
    Account.SubType.UNREALIZED_INVESTMENT_GAINS,
]

VALID_ENTRY_TYPES = {
    JournalEntryItem.JournalEntryType.DEBIT,
    JournalEntryItem.JournalEntryType.CREDIT,
}
ACTION_SET_ENTITY = "set_entity"
ACTION_CLEAR_ENTITY = "clear_entity"
ACTION_CHANGE_ACCOUNT = "change_account"
# A view operation only inspects the matched items; it never mutates the ledger,
# so it carries no Apply button and cannot be applied.
ACTION_VIEW = "view"

MUTATING_ACTIONS = {ACTION_SET_ENTITY, ACTION_CLEAR_ENTITY, ACTION_CHANGE_ACCOUNT}

SAMPLE_LIMIT = 25

# Revert is a near-term "oops" safety net, not a permanent audit log. Each apply
# records a RecharacterizeChange plus one RecharacterizeChangeItem per affected
# item, so we cap the history to the most recent N applied changes and prune the
# rest (cascading their items) to keep the snapshot tables bounded over time.
RECHARACTERIZE_HISTORY_LIMIT = 50


# --- Account / entity helpers ----------------------------------------------


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


# --- Operation evaluation (shared by preview and apply) ---------------------


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


# --- Preview ----------------------------------------------------------------


@dataclass
class PageResult:
    """One page of an operation's matched items, for inline paging.

    The adjacent page numbers are derivable (page ± 1, gated by
    ``has_previous``/``has_next``), so the template computes them rather than
    mirroring them here.
    """

    op_index: int
    rows: List[Dict[str, Any]]
    page: int
    num_pages: int
    total: int
    has_previous: bool
    has_next: bool


@dataclass
class OperationPreview:
    index: int
    criteria: List[Dict[str, str]]
    action_summary: str
    affected_count: int
    page: Optional[PageResult]
    blocked: bool
    error: Optional[str]
    mutates: bool = False


@dataclass
class PlanPreview:
    # Each operation carries its own blocked/mutates/affected_count state and its
    # own Apply button, so the plan holds no aggregate gate or totals.
    operations: List[OperationPreview]


def _project_row(item: JournalEntryItem, evaluation: EvaluatedOperation) -> Dict[str, Any]:
    """Projects one matched item to its before/after row for preview and export."""
    transaction = getattr(item.journal_entry, "transaction", None)
    description = (
        transaction.description if transaction else item.journal_entry.description
    )
    entity_before = item.entity.name if item.entity else "—"
    # Default to "no change", then let the action override its column, so a
    # view (or unrecognized action) shows the item untouched rather than
    # misprojecting.
    entity_after = entity_before
    account_after = item.account.name
    if evaluation.action_kind == ACTION_SET_ENTITY:
        entity_after = evaluation.target_entity.name
    elif evaluation.action_kind == ACTION_CLEAR_ENTITY:
        entity_after = "—"
    elif evaluation.action_kind == ACTION_CHANGE_ACCOUNT:
        account_after = evaluation.to_account.name
    return {
        "date": item.journal_entry.date,
        "description": description,
        "type": item.type,
        "amount": item.amount,
        "account_before": item.account.name,
        "account_after": account_after,
        "entity_before": entity_before,
        "entity_after": entity_after,
    }


def _page_result(
    evaluation: EvaluatedOperation,
    op_index: int,
    page_number: int,
    page_size: int = SAMPLE_LIMIT,
) -> PageResult:
    """Paginates an evaluated (non-blocked) operation's matched items."""
    paginator = Paginator(evaluation.queryset, page_size)
    page_obj = paginator.get_page(page_number)  # clamps invalid page numbers
    return PageResult(
        op_index=op_index,
        rows=[_project_row(item, evaluation) for item in page_obj.object_list],
        page=page_obj.number,
        num_pages=paginator.num_pages,
        total=paginator.count,
        has_previous=page_obj.has_previous(),
        has_next=page_obj.has_next(),
    )


def preview_plan(operations: List[Dict[str, Any]]) -> PlanPreview:
    """Validates every operation and computes its exact effect for review."""
    op_previews: List[OperationPreview] = []

    for index, operation in enumerate(operations):
        evaluation = _evaluate_operation(operation)
        if evaluation.blocked:
            op_previews.append(
                OperationPreview(
                    index=index,
                    criteria=evaluation.criteria,
                    action_summary=evaluation.action_summary,
                    affected_count=0,
                    page=None,
                    blocked=True,
                    error=" ".join(evaluation.errors),
                    mutates=False,
                )
            )
            continue

        page = _page_result(evaluation, index, 1)
        op_previews.append(
            OperationPreview(
                index=index,
                criteria=evaluation.criteria,
                action_summary=evaluation.action_summary,
                affected_count=page.total,
                page=page,
                blocked=False,
                error=None,
                mutates=_is_mutation(evaluation.action_kind),
            )
        )

    # Each mutating operation carries its own Apply button (see the preview
    # template), so there is no plan-wide apply gate; a blocked or view-only op
    # simply shows no button without affecting its siblings.
    return PlanPreview(operations=op_previews)


def _evaluate_at(
    operations: List[Dict[str, Any]], op_index: int
) -> Optional[EvaluatedOperation]:
    """Re-evaluates the operation at ``op_index`` from its dict (never trusts a
    stale preview). Returns None for an out-of-range index or a blocked op."""
    if op_index < 0 or op_index >= len(operations):
        return None
    evaluation = _evaluate_operation(operations[op_index])
    return None if evaluation.blocked else evaluation


def build_export_rows(
    operations: List[Dict[str, Any]], op_index: int
) -> List[Dict[str, Any]]:
    """Projects every matched item for one operation (no SAMPLE_LIMIT slice), so
    the export reflects the live ledger. Returns ``[]`` for an out-of-range index
    or a blocked operation."""
    evaluation = _evaluate_at(operations, op_index)
    if evaluation is None:
        return []
    return [_project_row(item, evaluation) for item in evaluation.queryset]


def build_page(
    operations: List[Dict[str, Any]],
    op_index: int,
    page_number: int,
    page_size: int = SAMPLE_LIMIT,
) -> Optional[PageResult]:
    """Projects one page of an operation's matched items for inline paging.

    Out-of-range page numbers are clamped; a blocked or out-of-range operation
    yields None.
    """
    evaluation = _evaluate_at(operations, op_index)
    if evaluation is None:
        return None
    return _page_result(evaluation, op_index, page_number, page_size)


# --- Apply ------------------------------------------------------------------


@dataclass
class ApplyResult:
    success: bool
    updated_count: int = 0
    action_summary: str = ""
    error: Optional[str] = None
    change_id: Optional[int] = None


def _summarize_criteria(criteria: List[Dict[str, str]]) -> str:
    """Flattens the labeled filter rows into one human-readable line for the log."""
    return "; ".join(f"{row['label']}: {row['value']}" for row in criteria)


def _record_change(
    evaluation: EvaluatedOperation, snapshot: List[Dict[str, Any]]
) -> RecharacterizeChange:
    """Records the pre-change snapshot, then prunes to the retention cap.

    ``snapshot`` is the matched items' before-state (pk + account/entity),
    materialized once by the caller and reused for both this record and the
    update. Must run inside apply's atomic block.
    """
    change = RecharacterizeChange.objects.create(
        action_kind=evaluation.action_kind,
        action_summary=evaluation.action_summary,
        criteria_summary=_summarize_criteria(evaluation.criteria),
        updated_count=len(snapshot),
        new_account=evaluation.to_account,
        new_entity=evaluation.target_entity,
    )
    RecharacterizeChangeItem.objects.bulk_create(
        [
            RecharacterizeChangeItem(
                change=change,
                journal_entry_item_id=row["pk"],
                prior_account_id=row["account_id"],
                prior_entity_id=row["entity_id"],
            )
            for row in snapshot
        ]
    )
    _prune_history()
    return change


def _prune_history() -> None:
    """Deletes applied changes beyond the most recent N (cascades their items)."""
    cutoff_ids = list(
        RecharacterizeChange.objects.order_by("-created_at", "-id").values_list(
            "id", flat=True
        )[RECHARACTERIZE_HISTORY_LIMIT:]
    )
    if cutoff_ids:
        RecharacterizeChange.objects.filter(id__in=cutoff_ids).delete()


@db_transaction.atomic
def apply_operation(operations: List[Dict[str, Any]], op_index: int) -> ApplyResult:
    """Re-validates and applies a single operation, leaving the rest untouched.

    Re-evaluates from the operation dict (never trusts a stale preview) so the
    write reflects the live ledger. Operations are applied one at a time, so a
    blocked sibling never prevents committing this one; the user resolves and
    applies each independently. The pre-change state is snapshotted into a
    RecharacterizeChange so the operation can later be reverted.
    """
    if op_index < 0 or op_index >= len(operations):
        return ApplyResult(success=False, error="There is nothing to apply.")

    evaluation = _evaluate_operation(operations[op_index])
    if evaluation.blocked:
        return ApplyResult(
            success=False,
            error="Operation blocked: " + " ".join(evaluation.errors),
        )

    if not _is_mutation(evaluation.action_kind):
        # A view-only operation has nothing to commit.
        return ApplyResult(
            success=False, error="This operation does not change anything."
        )

    # Materialize the matched items once: the snapshot feeds both the recorded
    # before-state and the update below, which targets those exact pks rather
    # than re-running the criteria filter a second time.
    snapshot = list(evaluation.queryset.values("pk", "account_id", "entity_id"))
    change = _record_change(evaluation, snapshot)
    matched = JournalEntryItem.objects.filter(pk__in=[row["pk"] for row in snapshot])

    if evaluation.action_kind == ACTION_SET_ENTITY:
        updated_count = matched.update(entity=evaluation.target_entity)
    elif evaluation.action_kind == ACTION_CLEAR_ENTITY:
        updated_count = matched.update(entity=None)
    elif evaluation.action_kind == ACTION_CHANGE_ACCOUNT:
        updated_count = matched.update(account=evaluation.to_account)
    else:  # pragma: no cover - mutation guard above keeps this unreachable
        return ApplyResult(success=False, error="This operation cannot be applied.")

    return ApplyResult(
        success=True,
        updated_count=updated_count,
        action_summary=evaluation.action_summary,
        change_id=change.id,
    )


# --- Revert -----------------------------------------------------------------


@dataclass
class RevertResult:
    success: bool
    reverted_count: int = 0
    conflict_count: int = 0
    missing_count: int = 0
    action_summary: str = ""
    error: Optional[str] = None


@db_transaction.atomic
def revert_change(change_id: int) -> RevertResult:
    """Restores the items a recorded change touched to their prior values.

    Only restores items this change still owns — an item whose current value no
    longer matches what this change set was changed again by a later operation
    and is skipped (counted as a conflict) rather than clobbered. Items deleted
    since are counted as missing. Idempotent guard: a change can be reverted once.
    """
    change = RecharacterizeChange.objects.filter(id=change_id).first()
    if change is None:
        return RevertResult(success=False, error="That change no longer exists.")
    if change.is_reverted:
        return RevertResult(
            success=False,
            action_summary=change.action_summary,
            error="That change has already been reverted.",
        )

    # Account swaps restore the account field; both entity actions restore the
    # entity field. Drive the restore generically off that one field so there's
    # a single conflict-check/restore path (not one per action kind).
    field = "account" if change.action_kind == ACTION_CHANGE_ACCOUNT else "entity"
    current_attr = f"{field}_id"
    new_value = getattr(change, f"new_{field}_id")

    items = change.items.select_related("journal_entry_item")
    to_update: List[JournalEntryItem] = []
    reverted = conflict = missing = 0

    for record in items:
        jei = record.journal_entry_item
        if jei is None:
            missing += 1
            continue
        if getattr(jei, current_attr) != new_value:
            # The item was changed again by a later operation; don't clobber it.
            conflict += 1
            continue
        setattr(jei, current_attr, getattr(record, f"prior_{field}_id"))
        to_update.append(jei)
        reverted += 1

    if to_update:
        JournalEntryItem.objects.bulk_update(to_update, [field])

    change.is_reverted = True
    change.reverted_at = timezone.now()
    change.save(update_fields=["is_reverted", "reverted_at"])

    return RevertResult(
        success=True,
        reverted_count=reverted,
        conflict_count=conflict,
        missing_count=missing,
        action_summary=change.action_summary,
    )


def list_recent_changes(limit: int = SAMPLE_LIMIT) -> List[RecharacterizeChange]:
    """Returns the most recent applied changes for the history panel (read-only)."""
    return list(
        RecharacterizeChange.objects.select_related("new_account", "new_entity")[:limit]
    )


# --- Chat turn orchestration ------------------------------------------------


@dataclass
class TurnResult:
    reply: str
    operations: List[Dict[str, Any]]
    error: Optional[str] = None
    # True when the Gemini call/parse raised — distinguishes a transient service
    # failure (retry) from a model reply the user should act on or rephrase.
    failed: bool = False


def _build_catalogs() -> Tuple[List[str], List[str], List[str]]:
    # Every account is available for entity tagging, so all names go in the
    # usable catalog. The swap-blocked subset is flagged separately so the LLM
    # knows those names may never be the source/target of an account swap.
    accounts = list(Account.objects.all().order_by("name"))
    account_names = [a.name for a in accounts]
    swap_blocked_names = [a.name for a in accounts if is_swap_blocked_account(a)]
    entity_names = list(Entity.objects.order_by("name").values_list("name", flat=True))
    return account_names, entity_names, swap_blocked_names


# --- Manual operation builder ----------------------------------------------
#
# The manual builder lets a user construct the exact same {filter, action}
# operation the LLM emits, by hand, with no model involved. The dict it produces
# flows through preview_plan / apply_operation / revert_change unchanged, so all
# guardrails apply identically whether an op came from the agent or the form.


@dataclass
class FormCatalogs:
    """Name lists for populating the manual builder's <select> inputs."""

    accounts: List[str]
    entities: List[str]
    swap_blocked: List[str]


def manual_form_catalogs() -> FormCatalogs:
    """Account/entity names for the manual builder, reusing the LLM catalogs."""
    account_names, entity_names, swap_blocked_names = _build_catalogs()
    return FormCatalogs(
        accounts=account_names,
        entities=entity_names,
        swap_blocked=swap_blocked_names,
    )


def build_manual_operation(data: Dict[str, Any]) -> Dict[str, Any]:
    """Builds a ``{filter, action}`` operation dict from cleaned form data.

    Mirrors the shape the LLM emits so the manual path reuses preview/apply
    unchanged. Empty fields are dropped so the no-filter guard and action_summary
    logic behave identically to an agent-proposed operation, and dates are stored
    as ISO strings to keep the session plan JSON-serializable. All semantic
    validation (swap-blocked accounts, type match, empty filter) is deferred to
    _evaluate_operation, which surfaces a blocked op in the preview.
    """
    filter_data: Dict[str, Any] = {}
    if data.get("description_contains"):
        filter_data["description_contains"] = data["description_contains"]
    if data.get("date_from"):
        filter_data["date_from"] = data["date_from"].isoformat()
    if data.get("date_to"):
        filter_data["date_to"] = data["date_to"].isoformat()
    # account/entity arrive as Account/Entity objects (multi-select); store the
    # names so the plan stays JSON-serializable and matches the LLM's by-name shape.
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


def run_turn(messages: List[Dict[str, str]]) -> TurnResult:
    """Sends the conversation to Gemini and parses its proposed plan.

    ``messages`` is the full chat history (including the latest user message).
    Returns the assistant's reply plus the structured operations it proposed.
    Never raises — model/parse failures degrade to a friendly reply.
    """
    account_names, entity_names, swap_blocked_names = _build_catalogs()
    system_prompt = gemini_services.build_recharacterize_system_prompt(
        account_names=account_names,
        entity_names=entity_names,
        swap_blocked_account_names=swap_blocked_names,
    )

    try:
        raw = gemini_services.call_gemini_conversation(system_prompt, messages)
        data = gemini_services._loads_gemini_json(raw)
    except Exception as exc:  # noqa: BLE001 - degrade gracefully for the UI
        logger.exception("Recharacterize turn failed")
        # No reply text: the UI renders a typed error banner + Retry from `error`.
        return TurnResult(
            reply="",
            operations=[],
            error=str(exc),
            failed=True,
        )

    reply = data.get("reply") or ""
    operations = data.get("operations")
    if not isinstance(operations, list):
        operations = []

    return TurnResult(reply=reply, operations=operations)
