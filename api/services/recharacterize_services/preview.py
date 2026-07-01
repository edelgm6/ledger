"""Preview, paging, and export projection.

Read-only projection of evaluated operations: the per-operation preview the plan
renders, plus the inline-paging and CSV-export helpers. No mutation here.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.core.paginator import Paginator

from api.models import JournalEntryItem

from .constants import (
    ACTION_CHANGE_ACCOUNT,
    ACTION_CLEAR_ENTITY,
    ACTION_SET_ENTITY,
    SAMPLE_LIMIT,
)
from .evaluation import EvaluatedOperation, _evaluate_operation
from .resolution import _is_mutation


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
    operations: List[Dict[str, Any]], op_index: Optional[int]
) -> Optional[EvaluatedOperation]:
    """Re-evaluates the operation at ``op_index`` from its dict (never trusts a
    stale preview). Returns None for a missing/out-of-range index or a blocked op,
    so callers can pass an unvalidated index straight through."""
    if op_index is None or op_index < 0 or op_index >= len(operations):
        return None
    evaluation = _evaluate_operation(operations[op_index])
    return None if evaluation.blocked else evaluation


def build_export_rows(
    operations: List[Dict[str, Any]], op_index: Optional[int]
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
    op_index: Optional[int],
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
