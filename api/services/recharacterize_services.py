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

from django.db import transaction as db_transaction
from django.db.models import QuerySet

from api.models import Account, Entity, JournalEntryItem
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

SAMPLE_LIMIT = 25


# --- Account / entity helpers ----------------------------------------------


def is_swap_blocked_account(account: Account) -> bool:
    return (
        account.special_type in SWAP_BLOCKED_SPECIAL_TYPES
        or account.sub_type in SWAP_BLOCKED_SUB_TYPES
    )


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
    account: Optional[Account],
    entity: Optional[Entity],
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
    if account:
        rows.append({"label": "Account", "value": account.name})
    if entity:
        rows.append({"label": "Current entity", "value": entity.name})
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

    # Resolve filter fields.
    description = filter_data.get("description_contains") or None
    filter_account, err = resolve_account(filter_data.get("account"))
    if err:
        result.errors.append(err)
    filter_entity, err = resolve_entity(filter_data.get("entity"))
    if err:
        result.errors.append(err)
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
        filter_account,
        filter_entity,
        entity_is_empty,
        entry_type,
    )

    # Guard against a filter that would match everything.
    has_any_filter = any(
        [
            description,
            date_from,
            date_to,
            filter_account,
            filter_entity,
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
    elif result.action_kind == ACTION_CHANGE_ACCOUNT:
        if filter_account is None:
            result.errors.append(
                "Changing an account requires a source account in the filter."
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
        account=filter_account,
        entity=filter_entity,
        entity_is_empty=entity_is_empty,
        entry_type=entry_type,
    )

    result.queryset = queryset
    return result


# --- Preview ----------------------------------------------------------------


@dataclass
class OperationPreview:
    index: int
    criteria: List[Dict[str, str]]
    action_summary: str
    affected_count: int
    sample: List[Dict[str, Any]]
    has_more: bool
    blocked: bool
    error: Optional[str]


@dataclass
class PlanPreview:
    operations: List[OperationPreview]
    total_affected: int
    has_blocks: bool
    can_apply: bool


def _build_sample(evaluation: EvaluatedOperation) -> List[Dict[str, Any]]:
    rows = []
    for item in evaluation.queryset[:SAMPLE_LIMIT]:
        transaction = getattr(item.journal_entry, "transaction", None)
        description = (
            transaction.description if transaction else item.journal_entry.description
        )
        entity_before = item.entity.name if item.entity else "—"
        # Default to "no change", then let the action override its column, so an
        # unrecognized action shows the item untouched rather than misprojecting.
        entity_after = entity_before
        account_after = item.account.name
        if evaluation.action_kind == ACTION_SET_ENTITY:
            entity_after = evaluation.target_entity.name
        elif evaluation.action_kind == ACTION_CLEAR_ENTITY:
            entity_after = "—"
        elif evaluation.action_kind == ACTION_CHANGE_ACCOUNT:
            account_after = evaluation.to_account.name
        rows.append(
            {
                "date": item.journal_entry.date,
                "description": description,
                "type": item.type,
                "amount": item.amount,
                "account_before": item.account.name,
                "account_after": account_after,
                "entity_before": entity_before,
                "entity_after": entity_after,
            }
        )
    return rows


def preview_plan(operations: List[Dict[str, Any]]) -> PlanPreview:
    """Validates every operation and computes its exact effect for review."""
    op_previews: List[OperationPreview] = []
    total_affected = 0
    has_blocks = False

    for index, operation in enumerate(operations):
        evaluation = _evaluate_operation(operation)
        if evaluation.blocked:
            has_blocks = True
            op_previews.append(
                OperationPreview(
                    index=index,
                    criteria=evaluation.criteria,
                    action_summary=evaluation.action_summary,
                    affected_count=0,
                    sample=[],
                    has_more=False,
                    blocked=True,
                    error=" ".join(evaluation.errors),
                )
            )
            continue

        affected_count = evaluation.queryset.count()
        total_affected += affected_count
        op_previews.append(
            OperationPreview(
                index=index,
                criteria=evaluation.criteria,
                action_summary=evaluation.action_summary,
                affected_count=affected_count,
                sample=_build_sample(evaluation),
                has_more=affected_count > SAMPLE_LIMIT,
                blocked=False,
                error=None,
            )
        )

    can_apply = bool(operations) and not has_blocks and total_affected > 0
    return PlanPreview(
        operations=op_previews,
        total_affected=total_affected,
        has_blocks=has_blocks,
        can_apply=can_apply,
    )


# --- Apply ------------------------------------------------------------------


@dataclass
class ApplyResult:
    success: bool
    updated_count: int = 0
    error: Optional[str] = None


@db_transaction.atomic
def apply_plan(operations: List[Dict[str, Any]]) -> ApplyResult:
    """Re-validates and applies every operation atomically.

    Re-evaluates from the operation dicts (never trusts a stale preview). If any
    operation is blocked, the whole plan aborts with no writes.
    """
    if not operations:
        return ApplyResult(success=False, error="There is nothing to apply.")

    evaluations = []
    for operation in operations:
        evaluation = _evaluate_operation(operation)
        if evaluation.blocked:
            return ApplyResult(
                success=False,
                error="Plan blocked: " + " ".join(evaluation.errors),
            )
        evaluations.append(evaluation)

    updated_count = 0
    for evaluation in evaluations:
        if evaluation.action_kind == ACTION_SET_ENTITY:
            updated_count += evaluation.queryset.update(
                entity=evaluation.target_entity
            )
        elif evaluation.action_kind == ACTION_CLEAR_ENTITY:
            updated_count += evaluation.queryset.update(entity=None)
        elif evaluation.action_kind == ACTION_CHANGE_ACCOUNT:
            updated_count += evaluation.queryset.update(
                account=evaluation.to_account
            )

    return ApplyResult(success=True, updated_count=updated_count)


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
