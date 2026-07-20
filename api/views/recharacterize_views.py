"""
Views for the agentic bulk-recharacterization tool.

HTTP orchestration only: parse requests, drive recharacterize_services, render
via recharacterize_helpers. The conversation and the latest proposed plan live
in the session; apply always re-validates from the stored plan.
"""

import csv

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.views import View

from api.forms import RecharacterizeOperationForm
from api.services import recharacterize_services
from api.views import recharacterize_helpers
from api.views.page_utils import render_full_page

SESSION_KEY = "recharacterize"


def _get_state(request) -> dict:
    return request.session.get(SESSION_KEY, {"messages": [], "operations": []})


def _save_state(request, messages, operations) -> None:
    request.session[SESSION_KEY] = {"messages": messages, "operations": operations}
    request.session.modified = True


def _parse_int_param(request, key: str, default: int = -1) -> int:
    """Reads a scalar int query param (``page``, ``change``), or ``default`` when
    absent/invalid. Operation indices go through ``_valid_op_index`` instead, which
    bounds-checks against the current plan."""
    try:
        return int(request.GET.get(key, ""))
    except (TypeError, ValueError):
        return default


def _render_main(
    messages,
    preview=None,
    *,
    flash=None,
    error=None,
    active_tab="manual",
    manual_form=None,
    catalogs=None,
    edit_index=None,
    edit_agent_error=None,
) -> str:
    """Renders the main region, always with the current history panel attached.

    Every render of #recharacterize-main must reflect the live history, so this
    is the single seam that fetches it — call sites never thread it themselves.
    ``active_tab`` keeps the agent or manual tab open across htmx swaps. The
    manual builder needs a form for its select options; a fresh one is built when
    none was threaded in (the invalid-submit and edit paths pass a bound/prefilled
    form). ``edit_index`` puts the manual builder in edit mode for that operation.

    The manual builder is always in the swapped DOM (a hidden tab), so its form —
    and the account/entity catalogs it needs — is built on every render. A view
    that already built the catalogs (to validate a submit or prefill an edit)
    threads them in via ``catalogs`` so the request queries them only once.
    """
    if manual_form is None:
        catalogs = catalogs or recharacterize_services.manual_form_catalogs()
        manual_form = RecharacterizeOperationForm(catalogs=catalogs)
    return recharacterize_helpers.render_main(
        messages,
        preview,
        flash=flash,
        error=error,
        history=recharacterize_services.list_recent_changes(),
        active_tab=active_tab,
        manual_form=manual_form,
        edit_index=edit_index,
        edit_agent_error=edit_agent_error,
    )


def _render_unchanged(messages, operations, *, active_tab="manual") -> str:
    """Re-renders the main region without running a turn (state untouched).

    ``active_tab`` defaults to the home (manual) pane; the agent chat flows pass
    ``"agent"`` so a no-op turn keeps the user on the chat.
    """
    preview = recharacterize_services.preview_plan(operations)
    return _render_main(messages, preview, active_tab=active_tab)


def _run_turn_and_render(request, messages, operations) -> str:
    """Runs one Gemini turn against ``messages`` and renders the main region.

    Shared by the message and retry views. ``operations`` is the plan already in
    the session: on a failed turn it is preserved (so a transient error never
    discards a proposed plan) and surfaced as a typed error banner with a Retry;
    on success the model's new plan replaces it.
    """
    turn = recharacterize_services.run_turn(messages)

    if turn.failed:
        # Keep the trailing user message so Retry can re-send it; don't add a
        # misleading assistant bubble. Hold onto the previously proposed plan.
        _save_state(request, messages=messages, operations=operations)
        preview = recharacterize_services.preview_plan(operations)
        error = recharacterize_helpers.build_turn_error(turn.error)
        return _render_main(messages, preview, error=error, active_tab="agent")

    messages.append({"role": "assistant", "text": turn.reply})
    preview = recharacterize_services.preview_plan(turn.operations)
    _save_state(request, messages=messages, operations=turn.operations)
    return _render_main(messages, preview, active_tab="agent")


class RecharacterizeView(LoginRequiredMixin, View):
    """Full page. A GET starts a fresh session."""

    login_url = "/login/"

    def get(self, request):
        _save_state(request, messages=[], operations=[])
        html = recharacterize_helpers.render_page(
            _render_main(messages=[], preview=None)
        )
        return render_full_page(request, html)


class RecharacterizeMessageView(LoginRequiredMixin, View):
    """Handles a chat message: ask the model, preview the proposed plan."""

    login_url = "/login/"

    def post(self, request):
        state = _get_state(request)
        messages = state["messages"]

        user_text = (request.POST.get("message") or "").strip()
        if not user_text:
            return HttpResponse(
                _render_unchanged(messages, state["operations"], active_tab="agent")
            )

        messages.append({"role": "user", "text": user_text})
        html = _run_turn_and_render(request, messages, state["operations"])
        return HttpResponse(html)


class RecharacterizeRetryView(LoginRequiredMixin, View):
    """Re-runs the last turn after a transient Gemini failure.

    Re-sends the trailing (unanswered) user message — no new message is appended.
    """

    login_url = "/login/"

    def post(self, request):
        state = _get_state(request)
        messages = state["messages"]

        if not messages or messages[-1]["role"] != "user":
            # Nothing to retry (no unanswered user turn); just re-render.
            return HttpResponse(
                _render_unchanged(messages, state["operations"], active_tab="agent")
            )

        html = _run_turn_and_render(request, messages, state["operations"])
        return HttpResponse(html)


def _valid_op_index(operations, raw):
    """Parses a POST/GET ``op`` value to a valid index, or None when absent/invalid.

    ``None`` is the same "no edit" contract the template and ``_render_main`` key
    off, so callers thread the result straight through without translating.
    """
    try:
        index = int(raw)
    except (TypeError, ValueError):
        return None
    return index if 0 <= index < len(operations) else None


def _prefilled_form(operations, edit_index, catalogs):
    """A manual form prefilled from the operation at ``edit_index`` (None if absent)."""
    if edit_index is None:
        return None
    return RecharacterizeOperationForm(
        initial=recharacterize_services.operation_to_form_initial(
            operations[edit_index]
        ),
        catalogs=catalogs,
    )


class RecharacterizeManualView(LoginRequiredMixin, View):
    """Adds or overwrites a manually built operation — no LLM involved.

    Builds a ``{filter, action}`` operation from the manual form. With a valid
    ``op`` index in the POST it overwrites that operation (edit mode); otherwise it
    appends. Then previews the plan. Semantic guardrails are enforced by
    preview_plan, so a swap-blocked / empty-filter / type-mismatch op renders as a
    blocked operation rather than erroring here.
    """

    login_url = "/login/"

    def post(self, request):
        state = _get_state(request)
        messages = state["messages"]
        operations = state["operations"]

        # Build the catalogs once and reuse them for both validating the bound form
        # and (on success) rendering the fresh builder, so the request queries the
        # account/entity lists a single time.
        catalogs = recharacterize_services.manual_form_catalogs()
        edit_index = _valid_op_index(operations, request.POST.get("op"))
        form = RecharacterizeOperationForm(request.POST, catalogs=catalogs)
        if not form.is_valid():
            # Re-render with field errors, keeping the user on the Manual tab (and
            # in edit mode when they were editing an existing operation).
            preview = (
                recharacterize_services.preview_plan(operations)
                if operations
                else None
            )
            html = _render_main(
                messages,
                preview,
                active_tab="manual",
                manual_form=form,
                edit_index=edit_index,
            )
            return HttpResponse(html)

        operation = recharacterize_services.build_manual_operation(form.cleaned_data)
        operations = list(operations)
        if edit_index is not None:
            operations[edit_index] = operation  # overwrite: keep its position
        else:
            operations.insert(0, operation)  # new op stacks on top (newest first)
        _save_state(request, messages=messages, operations=operations)
        preview = recharacterize_services.preview_plan(operations)
        # Saving exits edit mode back to the empty builder; appending stays there.
        return HttpResponse(
            _render_main(messages, preview, active_tab="manual", catalogs=catalogs)
        )


class RecharacterizeEditView(LoginRequiredMixin, View):
    """Opens the manual builder prefilled to edit one operation (or cancels).

    With a valid ``op`` index, prefills the builder from that operation and renders
    the Manual tab in edit mode. Without one (Cancel), renders a fresh builder. The
    session plan is never mutated here, so the preview is preserved either way.
    """

    login_url = "/login/"

    def get(self, request):
        state = _get_state(request)
        messages = state["messages"]
        operations = state["operations"]

        preview = (
            recharacterize_services.preview_plan(operations) if operations else None
        )
        # A valid ``op`` enters edit mode; its absence (Cancel) falls through to a
        # fresh builder. Either way the plan is untouched.
        catalogs = recharacterize_services.manual_form_catalogs()
        edit_index = _valid_op_index(operations, request.GET.get("op"))
        html = _render_main(
            messages,
            preview,
            active_tab="manual",
            manual_form=_prefilled_form(operations, edit_index, catalogs),
            catalogs=catalogs,
            edit_index=edit_index,
        )
        return HttpResponse(html)


class RecharacterizeEditAgentView(LoginRequiredMixin, View):
    """Scoped one-shot LLM edit of a single operation.

    Sends the targeted operation plus a plain-language instruction to Gemini and
    overwrites that one operation with the revised result. The main chat log is
    untouched. On a transient failure or a non-answer, stays in edit mode and
    surfaces the issue.
    """

    login_url = "/login/"

    def post(self, request):
        state = _get_state(request)
        messages = state["messages"]
        operations = state["operations"]

        edit_index = _valid_op_index(operations, request.GET.get("op"))
        instruction = (request.POST.get("instruction") or "").strip()
        edit_agent_error = None

        if edit_index is not None and instruction:
            result = recharacterize_services.revise_operation(
                operations[edit_index], instruction
            )
            if result.success:
                # Overwrite just this op; stay in edit mode re-prefilled from the
                # revised op so the user can keep tweaking it.
                operations = list(operations)
                operations[edit_index] = result.operation
                _save_state(request, messages=messages, operations=operations)
            elif result.failed:
                edit_agent_error = "The agent couldn't be reached. Please try again."
            else:
                edit_agent_error = result.message

        preview = (
            recharacterize_services.preview_plan(operations) if operations else None
        )
        catalogs = recharacterize_services.manual_form_catalogs()
        return HttpResponse(
            _render_main(
                messages,
                preview,
                active_tab="manual",
                edit_index=edit_index,
                manual_form=_prefilled_form(operations, edit_index, catalogs),
                catalogs=catalogs,
                edit_agent_error=edit_agent_error,
            )
        )


class RecharacterizeApplyView(LoginRequiredMixin, View):
    """Re-validates and applies a single operation from the stored plan.

    Operations are applied one at a time: the ``op`` index selects which one.
    On success that operation is dropped from the plan and the remaining ops are
    re-previewed against the now-updated ledger.
    """

    login_url = "/login/"

    def post(self, request):
        state = _get_state(request)
        messages = state["messages"]
        operations = state["operations"]

        op_index = _valid_op_index(operations, request.GET.get("op"))
        if op_index is None:
            return HttpResponse(_render_unchanged(messages, operations))

        result = recharacterize_services.apply_operation(operations, op_index)

        if not result.success:
            # Surface the apply error as an assistant message so it's visible.
            messages.append({"role": "assistant", "text": result.error})
            _save_state(request, messages=messages, operations=operations)
            preview = recharacterize_services.preview_plan(operations)
            return HttpResponse(_render_main(messages, preview))

        # Drop the applied operation; the rest stay so they can be applied next.
        remaining = operations[:op_index] + operations[op_index + 1 :]
        # The confirmation lives in the chat log (consistent with every other
        # turn); the remaining-ops preview re-renders below it.
        messages.append(
            {
                "role": "assistant",
                "text": (
                    f"Applied: {result.action_summary}. Updated "
                    f"{result.updated_count} journal entry "
                    f"item{'' if result.updated_count == 1 else 's'}."
                ),
            }
        )
        _save_state(request, messages=messages, operations=remaining)
        preview = recharacterize_services.preview_plan(remaining) if remaining else None
        return HttpResponse(_render_main(messages, preview))


class RecharacterizeRevertView(LoginRequiredMixin, View):
    """Reverts a previously applied operation from the persisted history.

    Restores the items the change still owns to their prior values, records the
    outcome in the chat log, and re-renders the main region (history panel
    included) so the change now shows as reverted.
    """

    login_url = "/login/"

    def post(self, request):
        state = _get_state(request)
        messages = state["messages"]
        operations = state["operations"]

        change_id = _parse_int_param(request, "change")
        result = recharacterize_services.revert_change(change_id)

        if not result.success:
            messages.append({"role": "assistant", "text": result.error})
        else:
            note = (
                f"Reverted: {result.action_summary}. "
                f"Restored {result.reverted_count} journal entry "
                f"item{'' if result.reverted_count == 1 else 's'}."
            )
            if result.conflict_count:
                note += f" {result.conflict_count} skipped (changed since)."
            if result.missing_count:
                note += f" {result.missing_count} no longer exist."
            messages.append({"role": "assistant", "text": note})

        _save_state(request, messages=messages, operations=operations)
        preview = (
            recharacterize_services.preview_plan(operations) if operations else None
        )
        return HttpResponse(_render_main(messages, preview))


class RecharacterizePageView(LoginRequiredMixin, View):
    """Returns one paginated page of an operation's matched items.

    Lets the user expand past the 25-row preview sample and page through the full
    matched set inline (read-only; no mutation).
    """

    login_url = "/login/"

    def get(self, request):
        state = _get_state(request)
        operations = state["operations"]

        op_index = _valid_op_index(operations, request.GET.get("op"))
        page_number = _parse_int_param(request, "page", default=1)

        page = recharacterize_services.build_page(operations, op_index, page_number)
        html = recharacterize_helpers.render_affected_page(page)
        return HttpResponse(html)


class RecharacterizeExportView(LoginRequiredMixin, View):
    """Streams every matched item for one operation as a CSV download.

    The preview table is capped at SAMPLE_LIMIT rows; this exposes the full
    matched universe (with proposed before/after columns) for an operation.
    """

    login_url = "/login/"

    def get(self, request):
        state = _get_state(request)
        operations = state["operations"]

        op_index = _valid_op_index(operations, request.GET.get("op"))
        rows = recharacterize_services.build_export_rows(operations, op_index)

        response = HttpResponse(
            content_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="recharacterize.csv"'
            },
        )
        writer = csv.writer(response)
        writer.writerow(
            [
                "Date",
                "Description",
                "Type",
                "Amount",
                "Account Before",
                "Account After",
                "Entity Before",
                "Entity After",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["date"],
                    row["description"],
                    row["type"],
                    row["amount"],
                    row["account_before"],
                    row["account_after"],
                    row["entity_before"],
                    row["entity_after"],
                ]
            )
        return response


class RecharacterizeResetView(LoginRequiredMixin, View):
    """Clears the conversation and proposed plan."""

    login_url = "/login/"

    def post(self, request):
        _save_state(request, messages=[], operations=[])
        return HttpResponse(_render_main(messages=[], preview=None))
