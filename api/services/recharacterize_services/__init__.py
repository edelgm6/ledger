"""Service layer for the agentic bulk-recharacterization tool.

A user describes, in plain language, which journal entry items to target and what
change to make. The LLM (see gemini_services) only proposes a structured plan — a
list of ``{filter, action}`` operations. Everything in this package is
deterministic: it resolves names, enforces guardrails that protect book integrity,
previews the exact effect, and applies it atomically.

The module was split into focused submodules; this package re-exports the public
surface so callers keep importing ``api.services.recharacterize_services`` exactly
as before. Layering within the package:

    constants → resolution → evaluation → preview
                          ↘ evaluation → apply
                          ↘ llm (turn orchestration + manual builder)
"""

# Re-exported so test patches of
# ``api.services.recharacterize_services.gemini_services.<fn>`` resolve to the
# same module object the llm submodule calls into.
from api.services import gemini_services

from .apply import (
    ApplyResult,
    RevertResult,
    apply_operation,
    list_recent_changes,
    revert_change,
)
from .constants import (
    ACTION_CHANGE_ACCOUNT,
    ACTION_CLEAR_ENTITY,
    ACTION_SET_ENTITY,
    ACTION_VIEW,
    MUTATING_ACTIONS,
    RECHARACTERIZE_HISTORY_LIMIT,
    SAMPLE_LIMIT,
    SWAP_BLOCKED_SPECIAL_TYPES,
    SWAP_BLOCKED_SUB_TYPES,
    VALID_ENTRY_TYPES,
)
from .evaluation import EvaluatedOperation, _evaluate_operation
from .llm import (
    FormCatalogs,
    RevisedOperation,
    TurnResult,
    build_manual_operation,
    manual_form_catalogs,
    operation_to_form_initial,
    revise_operation,
    run_turn,
)
from .preview import (
    OperationPreview,
    PageResult,
    PlanPreview,
    build_export_rows,
    build_page,
    preview_plan,
)
from .resolution import (
    is_swap_blocked_account,
    resolve_account,
    resolve_entity,
)

__all__ = [
    "gemini_services",
    # constants
    "ACTION_CHANGE_ACCOUNT",
    "ACTION_CLEAR_ENTITY",
    "ACTION_SET_ENTITY",
    "ACTION_VIEW",
    "MUTATING_ACTIONS",
    "RECHARACTERIZE_HISTORY_LIMIT",
    "SAMPLE_LIMIT",
    "SWAP_BLOCKED_SPECIAL_TYPES",
    "SWAP_BLOCKED_SUB_TYPES",
    "VALID_ENTRY_TYPES",
    # resolution
    "is_swap_blocked_account",
    "resolve_account",
    "resolve_entity",
    # evaluation
    "EvaluatedOperation",
    "_evaluate_operation",
    # preview
    "OperationPreview",
    "PageResult",
    "PlanPreview",
    "build_export_rows",
    "build_page",
    "preview_plan",
    # apply / revert
    "ApplyResult",
    "RevertResult",
    "apply_operation",
    "list_recent_changes",
    "revert_change",
    # llm / manual builder
    "FormCatalogs",
    "RevisedOperation",
    "TurnResult",
    "build_manual_operation",
    "manual_form_catalogs",
    "operation_to_form_initial",
    "revise_operation",
    "run_turn",
]
