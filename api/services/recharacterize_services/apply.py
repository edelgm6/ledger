"""The mutation lifecycle: apply one operation, revert a recorded change, and
list recent changes.

Both apply and revert run in atomic blocks and snapshot enough before-state into
RecharacterizeChange / RecharacterizeChangeItem to undo an apply later.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.db import transaction as db_transaction
from django.utils import timezone

from api.models import (
    JournalEntryItem,
    RecharacterizeChange,
    RecharacterizeChangeItem,
)

from .constants import (
    ACTION_CHANGE_ACCOUNT,
    ACTION_CLEAR_ENTITY,
    ACTION_SET_ENTITY,
    RECHARACTERIZE_HISTORY_LIMIT,
    SAMPLE_LIMIT,
)
from .evaluation import EvaluatedOperation, _evaluate_operation
from .resolution import _is_mutation


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
