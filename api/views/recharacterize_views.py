"""
Views for the agentic bulk-recharacterization tool.

HTTP orchestration only: parse requests, drive recharacterize_services, render
via recharacterize_helpers. The conversation and the latest proposed plan live
in the session; apply always re-validates from the stored plan.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.views import View

from api.services import recharacterize_services
from api.views import recharacterize_helpers
from api.views.page_utils import render_full_page

SESSION_KEY = "recharacterize"


def _get_state(request) -> dict:
    return request.session.get(SESSION_KEY, {"messages": [], "operations": []})


def _save_state(request, messages, operations) -> None:
    request.session[SESSION_KEY] = {"messages": messages, "operations": operations}
    request.session.modified = True


def _render_unchanged(messages, operations) -> str:
    """Re-renders the main region without running a turn (state untouched)."""
    preview = recharacterize_services.preview_plan(operations)
    return recharacterize_helpers.render_main(messages, preview)


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
        return recharacterize_helpers.render_main(messages, preview, error=error)

    messages.append({"role": "assistant", "text": turn.reply})
    preview = recharacterize_services.preview_plan(turn.operations)
    _save_state(request, messages=messages, operations=turn.operations)
    return recharacterize_helpers.render_main(messages, preview)


class RecharacterizeView(LoginRequiredMixin, View):
    """Full page. A GET starts a fresh session."""

    login_url = "/login/"

    def get(self, request):
        _save_state(request, messages=[], operations=[])
        html = recharacterize_helpers.render_page(messages=[], preview=None)
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


class RecharacterizeApplyView(LoginRequiredMixin, View):
    """Re-validates and applies the plan stored in the session."""

    login_url = "/login/"

    def post(self, request):
        state = _get_state(request)
        messages = state["messages"]
        operations = state["operations"]

        result = recharacterize_services.apply_plan(operations)

        if not result.success:
            # Surface the apply error as an assistant message so it's visible.
            messages.append({"role": "assistant", "text": result.error})
            _save_state(request, messages=messages, operations=operations)
            preview = recharacterize_services.preview_plan(operations)
            html = recharacterize_helpers.render_main(messages, preview)
            return HttpResponse(html)

        flash = (
            f"Applied. Updated {result.updated_count} journal entry "
            f"item{'' if result.updated_count == 1 else 's'}."
        )
        messages.append({"role": "assistant", "text": flash})
        _save_state(request, messages=messages, operations=[])
        html = recharacterize_helpers.render_main(messages, preview=None, flash=flash)
        return HttpResponse(html)


class RecharacterizeResetView(LoginRequiredMixin, View):
    """Clears the conversation and proposed plan."""

    login_url = "/login/"

    def post(self, request):
        _save_state(request, messages=[], operations=[])
        html = recharacterize_helpers.render_main(messages=[], preview=None)
        return HttpResponse(html)
