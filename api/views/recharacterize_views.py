"""
Views for the bulk-recharacterization tool.

HTTP orchestration only: parse requests, drive recharacterize_services, render
via recharacterize_helpers. The latest proposed plan lives in the session; apply
always re-validates from the stored plan.
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
    return request.session.get(SESSION_KEY, {"operations": []})


def _save_state(request, operations) -> None:
    request.session[SESSION_KEY] = {"operations": operations}
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
    preview=None,
    *,
    flash=None,
    flash_error=None,
    manual_form=None,
    catalogs=None,
    edit_index=None,
) -> str:
    """Renders the main region, always with the current history panel attached.

    Every render of #recharacterize-main must reflect the live history, so this
    is the single seam that fetches it — call sites never thread it themselves.
    The manual builder needs a form for its select options; a fresh one is built
    when none was threaded in (the invalid-submit and edit paths pass a
    bound/prefilled form). ``edit_index`` puts the manual builder in edit mode for
    that operation. ``flash`` / ``flash_error`` surface an apply/revert outcome
    above the preview.

    A view that already built the account/entity catalogs (to validate a submit or
    prefill an edit) threads them in via ``catalogs`` so the request queries them
    only once.
    """
    if manual_form is None:
        catalogs = catalogs or recharacterize_services.manual_form_catalogs()
        manual_form = RecharacterizeOperationForm(catalogs=catalogs)
    return recharacterize_helpers.render_main(
        preview,
        flash=flash,
        flash_error=flash_error,
        history=recharacterize_services.list_recent_changes(),
        manual_form=manual_form,
        edit_index=edit_index,
    )


class RecharacterizeView(LoginRequiredMixin, View):
    """Full page. A GET starts a fresh session."""

    login_url = "/login/"

    def get(self, request):
        _save_state(request, operations=[])
        html = recharacterize_helpers.render_page(_render_main(preview=None))
        return render_full_page(request, html)


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
    """Adds or overwrites a manually built operation.

    Builds a ``{filter, action}`` operation from the manual form. With a valid
    ``op`` index in the POST it overwrites that operation (edit mode); otherwise it
    appends. Then previews the plan. Semantic guardrails are enforced by
    preview_plan, so a swap-blocked / empty-filter / type-mismatch op renders as a
    blocked operation rather than erroring here.
    """

    login_url = "/login/"

    def post(self, request):
        state = _get_state(request)
        operations = state["operations"]

        # Build the catalogs once and reuse them for both validating the bound form
        # and (on success) rendering the fresh builder, so the request queries the
        # account/entity lists a single time.
        catalogs = recharacterize_services.manual_form_catalogs()
        edit_index = _valid_op_index(operations, request.POST.get("op"))
        form = RecharacterizeOperationForm(request.POST, catalogs=catalogs)
        if not form.is_valid():
            # Re-render with field errors, staying in edit mode when they were
            # editing an existing operation.
            preview = (
                recharacterize_services.preview_plan(operations)
                if operations
                else None
            )
            html = _render_main(
                preview,
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
        _save_state(request, operations=operations)
        preview = recharacterize_services.preview_plan(operations)
        # Saving exits edit mode back to the empty builder; appending stays there.
        return HttpResponse(_render_main(preview, catalogs=catalogs))


class RecharacterizeEditView(LoginRequiredMixin, View):
    """Opens the manual builder prefilled to edit one operation (or cancels).

    With a valid ``op`` index, prefills the builder from that operation and renders
    it in edit mode. Without one (Cancel), renders a fresh builder. The session
    plan is never mutated here, so the preview is preserved either way.
    """

    login_url = "/login/"

    def get(self, request):
        state = _get_state(request)
        operations = state["operations"]

        preview = (
            recharacterize_services.preview_plan(operations) if operations else None
        )
        # A valid ``op`` enters edit mode; its absence (Cancel) falls through to a
        # fresh builder. Either way the plan is untouched.
        catalogs = recharacterize_services.manual_form_catalogs()
        edit_index = _valid_op_index(operations, request.GET.get("op"))
        html = _render_main(
            preview,
            manual_form=_prefilled_form(operations, edit_index, catalogs),
            catalogs=catalogs,
            edit_index=edit_index,
        )
        return HttpResponse(html)


class RecharacterizeApplyView(LoginRequiredMixin, View):
    """Re-validates and applies a single operation from the stored plan.

    Operations are applied one at a time: the ``op`` index selects which one.
    On success that operation is dropped from the plan and the remaining ops are
    re-previewed against the now-updated ledger.
    """

    login_url = "/login/"

    def post(self, request):
        state = _get_state(request)
        operations = state["operations"]

        op_index = _valid_op_index(operations, request.GET.get("op"))
        if op_index is None:
            preview = recharacterize_services.preview_plan(operations)
            return HttpResponse(_render_main(preview))

        result = recharacterize_services.apply_operation(operations, op_index)

        if not result.success:
            # Surface the apply error above the preview so it's visible.
            preview = recharacterize_services.preview_plan(operations)
            return HttpResponse(_render_main(preview, flash_error=result.error))

        # Drop the applied operation; the rest stay so they can be applied next.
        remaining = operations[:op_index] + operations[op_index + 1 :]
        flash = (
            f"Applied: {result.action_summary}. Updated "
            f"{result.updated_count} journal entry "
            f"item{'' if result.updated_count == 1 else 's'}."
        )
        _save_state(request, operations=remaining)
        preview = recharacterize_services.preview_plan(remaining) if remaining else None
        return HttpResponse(_render_main(preview, flash=flash))


class RecharacterizeRevertView(LoginRequiredMixin, View):
    """Reverts a previously applied operation from the persisted history.

    Restores the items the change still owns to their prior values, surfaces the
    outcome above the preview, and re-renders the main region (history panel
    included) so the change now shows as reverted.
    """

    login_url = "/login/"

    def post(self, request):
        state = _get_state(request)
        operations = state["operations"]

        change_id = _parse_int_param(request, "change")
        result = recharacterize_services.revert_change(change_id)

        flash = flash_error = None
        if not result.success:
            flash_error = result.error
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
            flash = note

        preview = (
            recharacterize_services.preview_plan(operations) if operations else None
        )
        return HttpResponse(_render_main(preview, flash=flash, flash_error=flash_error))


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
    """Clears the proposed plan."""

    login_url = "/login/"

    def post(self, request):
        _save_state(request, operations=[])
        return HttpResponse(_render_main(preview=None))
