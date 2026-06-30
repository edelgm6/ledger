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
    """Reads a query param as an int, or ``default`` when absent/invalid."""
    try:
        return int(request.GET.get(key, ""))
    except (TypeError, ValueError):
        return default


def _render_main(
    messages, preview=None, *, flash=None, error=None, active_tab="agent", manual_form=None
) -> str:
    """Renders the main region, always with the current history panel attached.

    Every render of #recharacterize-main must reflect the live history, so this
    is the single seam that fetches it — call sites never thread it themselves.
    ``active_tab`` keeps the agent or manual tab open across htmx swaps. The
    manual builder needs a form for its select options; a fresh one is built when
    none was threaded in (the invalid-submit path passes a bound form for errors).
    """
    form = manual_form or RecharacterizeOperationForm(
        catalogs=recharacterize_services.manual_form_catalogs()
    )
    return recharacterize_helpers.render_main(
        messages,
        preview,
        flash=flash,
        error=error,
        history=recharacterize_services.list_recent_changes(),
        active_tab=active_tab,
        manual_form=form,
    )


def _render_unchanged(messages, operations) -> str:
    """Re-renders the main region without running a turn (state untouched)."""
    preview = recharacterize_services.preview_plan(operations)
    return _render_main(messages, preview)


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
        return _render_main(messages, preview, error=error)

    messages.append({"role": "assistant", "text": turn.reply})
    preview = recharacterize_services.preview_plan(turn.operations)
    _save_state(request, messages=messages, operations=turn.operations)
    return _render_main(messages, preview)


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
            return HttpResponse(_render_unchanged(messages, state["operations"]))

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
            return HttpResponse(_render_unchanged(messages, state["operations"]))

        html = _run_turn_and_render(request, messages, state["operations"])
        return HttpResponse(html)


class RecharacterizeManualView(LoginRequiredMixin, View):
    """Appends a manually built operation to the plan — no LLM involved.

    Builds a ``{filter, action}`` operation from the manual form and appends it to
    the session plan, then previews it alongside any existing operations. Semantic
    guardrails are enforced by preview_plan, so a swap-blocked / empty-filter /
    type-mismatch op renders as a blocked operation rather than erroring here.
    """

    login_url = "/login/"

    def post(self, request):
        state = _get_state(request)
        messages = state["messages"]
        operations = state["operations"]

        form = RecharacterizeOperationForm(request.POST)
        if not form.is_valid():
            # Re-render with field errors, keeping the user on the Manual tab.
            preview = (
                recharacterize_services.preview_plan(operations)
                if operations
                else None
            )
            html = _render_main(
                messages, preview, active_tab="manual", manual_form=form
            )
            return HttpResponse(html)

        operation = recharacterize_services.build_manual_operation(form.cleaned_data)
        operations = operations + [operation]
        _save_state(request, messages=messages, operations=operations)
        preview = recharacterize_services.preview_plan(operations)
        return HttpResponse(_render_main(messages, preview, active_tab="manual"))


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

        op_index = _parse_int_param(request, "op")
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

        op_index = _parse_int_param(request, "op")
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

        op_index = _parse_int_param(request, "op")
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
