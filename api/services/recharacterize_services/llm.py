"""LLM turn orchestration and the manual operation builder.

The agent path (``run_turn`` / ``revise_operation``) and the manual path
(``build_manual_operation`` / ``operation_to_form_initial``) both produce the same
``{filter, action}`` dict, so everything downstream (preview/apply/revert) treats
agent- and hand-built operations identically.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from api.models import Account, Entity
from api.services import gemini_services

from .constants import ACTION_CHANGE_ACCOUNT, ACTION_SET_ENTITY, ACTION_VIEW
from .resolution import _as_name_list, _build_catalogs

logger = logging.getLogger(__name__)


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


def _name_pks(model, value: Any) -> List[str]:
    """Resolves a filter's account/entity names to a list of string PKs.

    The manual form's multi-selects mark an option selected via
    ``option.pk|stringformat:"s" in field.value`` (see typeahead-multiselect.html),
    so an unbound form's ``initial`` must carry string PKs — not instances or ints
    — for prefilled values to render as selected. Names that no longer resolve are
    dropped (the user re-picks them).
    """
    names = _as_name_list(value)
    if not names:
        return []
    pks = model.objects.filter(name__in=names).values_list("pk", flat=True)
    return [str(pk) for pk in pks]


def operation_to_form_initial(operation: Dict[str, Any]) -> Dict[str, Any]:
    """Reverse of ``build_manual_operation``: an ``initial`` dict for the manual
    form, used to prefill the builder when editing an existing operation.

    Dates stay ISO strings (an ``<input type=date>`` renders them as-is); account
    and entity become string-PK lists for the multi-selects; the action and its
    single-valued target/destination names pass straight through.
    """
    filter_data = operation.get("filter") or {}
    action_data = operation.get("action") or {}

    return {
        "description_contains": filter_data.get("description_contains") or "",
        "date_from": filter_data.get("date_from") or "",
        "date_to": filter_data.get("date_to") or "",
        "account": _name_pks(Account, filter_data.get("account")),
        "entity": _name_pks(Entity, filter_data.get("entity")),
        "entity_is_empty": bool(filter_data.get("entity_is_empty")),
        "entry_type": filter_data.get("entry_type") or "",
        "action_type": action_data.get("type") or ACTION_VIEW,
        "target_entity": action_data.get("entity") or "",
        "to_account": action_data.get("to_account") or "",
    }


# --- Chat turn orchestration ------------------------------------------------


@dataclass
class TurnResult:
    reply: str
    operations: List[Dict[str, Any]]
    error: Optional[str] = None
    # True when the Gemini call/parse raised — distinguishes a transient service
    # failure (retry) from a model reply the user should act on or rephrase.
    failed: bool = False


@dataclass
class RevisedOperation:

    success: bool
    operation: Optional[Dict[str, Any]] = None
    # A hint to surface when the model declined to revise (e.g. it asked a
    # clarifying question instead of returning an operation).
    message: Optional[str] = None
    # True when the Gemini call/parse raised — a transient failure the UI offers
    # to retry, distinct from a model reply the user should act on.
    failed: bool = False


def _call_recharacterize_gemini(
    messages: List[Dict[str, str]],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Builds the system prompt from the live catalogs, sends ``messages`` to
    Gemini, and parses the JSON reply.

    The single seam shared by ``run_turn`` (full conversation) and
    ``revise_operation`` (one synthetic turn): both need the same catalogs,
    system prompt, call, and degrade-on-error contract; they differ only in how
    they shape ``messages`` and interpret the parsed dict. Returns ``(data, None)``
    on success or ``(None, error)`` when the call/parse raised — never raises.
    """
    account_names, entity_names, swap_blocked_names = _build_catalogs()
    system_prompt = gemini_services.build_recharacterize_system_prompt(
        account_names=account_names,
        entity_names=entity_names,
        swap_blocked_account_names=swap_blocked_names,
    )
    try:
        raw = gemini_services.call_gemini_conversation(system_prompt, messages)
        return gemini_services.loads_gemini_json(raw), None
    except Exception as exc:  # noqa: BLE001 - degrade gracefully for the UI
        logger.exception("Recharacterize Gemini call failed")
        return None, str(exc)


def revise_operation(operation: Dict[str, Any], instruction: str) -> RevisedOperation:
    """Asks Gemini to revise one operation per a plain-language instruction.

    Reuses the recharacterize system prompt (so the same schema, catalogs, and
    guardrails apply) and sends a single synthetic turn carrying the current
    operation plus the instruction. Returns exactly one revised operation, which
    the caller overwrites in place. Never raises — failures degrade to a typed
    result for the UI.
    """
    user_text = (
        "Here is one existing operation as JSON:\n"
        f"{json.dumps(operation)}\n\n"
        f"Modify it as follows: {instruction}\n\n"
        "Return exactly ONE updated operation in the operations list (the full "
        "revised operation, not just the changed fields)."
    )
    data, error = _call_recharacterize_gemini([{"role": "user", "text": user_text}])
    if error is not None:
        return RevisedOperation(success=False, message=error, failed=True)

    operations = data.get("operations")
    if not isinstance(operations, list) or not operations:
        # The model returned no operation — usually because it needs the request
        # clarified. Surface its reply so the user can rephrase the instruction.
        return RevisedOperation(
            success=False,
            message=data.get("reply") or "The agent did not return a revised operation.",
        )

    return RevisedOperation(success=True, operation=operations[0])


def run_turn(messages: List[Dict[str, str]]) -> TurnResult:
    """Sends the conversation to Gemini and parses its proposed plan.

    ``messages`` is the full chat history (including the latest user message).
    Returns the assistant's reply plus the structured operations it proposed.
    Never raises — model/parse failures degrade to a friendly reply.
    """
    data, error = _call_recharacterize_gemini(messages)
    if error is not None:
        # No reply text: the UI renders a typed error banner + Retry from `error`.
        return TurnResult(reply="", operations=[], error=error, failed=True)

    reply = data.get("reply") or ""
    operations = data.get("operations")
    if not isinstance(operations, list):
        operations = []

    return TurnResult(reply=reply, operations=operations)
