"""Service layer for the bulk-recharacterization tool.

A user builds a structured plan — a list of ``{filter, action}`` operations —
with the manual builder. Everything in this package is deterministic: it resolves
names, enforces guardrails that protect book integrity, previews the exact
effect, and applies it atomically.

The module was split into focused submodules; this package re-exports the public
surface so callers keep importing ``api.services.recharacterize_services`` exactly
as before. Layering within the package:

    constants → resolution → evaluation → preview
                          ↘ evaluation → apply
                          ↘ builder (form input → operation)
"""

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
    SWAP_BLOCKED_SUB_TYPES,
    SWAP_BLOCKED_SYSTEM_ROLES,
    VALID_ENTRY_TYPES,
)
from .evaluation import EvaluatedOperation, _evaluate_operation
from .builder import (
    FormCatalogs,
    build_manual_operation,
    manual_form_catalogs,
    operation_to_form_initial,
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
    # constants
    "ACTION_CHANGE_ACCOUNT",
    "ACTION_CLEAR_ENTITY",
    "ACTION_SET_ENTITY",
    "ACTION_VIEW",
    "MUTATING_ACTIONS",
    "RECHARACTERIZE_HISTORY_LIMIT",
    "SAMPLE_LIMIT",
    "SWAP_BLOCKED_SUB_TYPES",
    "SWAP_BLOCKED_SYSTEM_ROLES",
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
    # manual builder
    "FormCatalogs",
    "build_manual_operation",
    "manual_form_catalogs",
    "operation_to_form_initial",
]
