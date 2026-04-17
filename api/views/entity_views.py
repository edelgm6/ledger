"""
Views for entity tagging and payables/receivables management.

These views handle HTTP orchestration, delegating business logic to services
and rendering to helpers.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from api.forms import JournalEntryItemEntityForm
from api.models import JournalEntryItem
from api.services import entity_services
from api.views import entity_helpers


def _render_full_page(
    is_initial_load: bool = False,
    preloaded_entity=None,
    preselected_entity=None,
    hide_zero: bool = True,
) -> str:
    """
    Helper to render the full entities page.

    Args:
        is_initial_load: Whether this is the initial page load (shows header)
        preloaded_entity: Entity to pre-select in the form dropdown
        preselected_entity: Entity to highlight in the balances table
        hide_zero: Whether to hide $0-balance entities in the grouped view
    """
    # Get data via services
    untagged = entity_services.get_untagged_journal_entry_items()
    grouped_balances = entity_services.get_grouped_entities_balances(
        hide_zero=hide_zero
    )

    # Get history if entity selected
    history_html = ""
    if preselected_entity:
        history_data = entity_services.get_entity_history(preselected_entity.id)
        history_html = entity_helpers.render_entity_history_table(history_data)

    # Render via helpers
    table_html = entity_helpers.render_untagged_entries_table(untagged.items)

    form_html = None
    if untagged.first_item:
        form_html = entity_helpers.render_entity_tag_form(
            untagged.first_item, preloaded_entity
        )

    balances_html = entity_helpers.render_entity_grouped_balances_table(
        grouped_balances, hide_zero, history_html
    )

    return entity_helpers.render_entity_page(
        table_html, form_html, balances_html, is_initial_load
    )


class UntagJournalEntryView(LoginRequiredMixin, View):
    """Removes entity assignment from a journal entry item."""

    login_url = "/login/"
    redirect_field_name = "next"

    def post(self, request, journal_entry_item_id):
        entity = entity_services.untag_journal_entry_item(journal_entry_item_id)
        html = _render_full_page(preselected_entity=entity)
        return HttpResponse(html)


class EntityHistoryTable(LoginRequiredMixin, View):
    """Returns the history table for a specific entity."""

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, entity_id):
        account_id_str = request.GET.get("account")
        account_id = int(account_id_str) if account_id_str else None
        history_data = entity_services.get_entity_history(entity_id, account_id)
        html = entity_helpers.render_entity_history_table(history_data)
        return HttpResponse(html)


class TagEntitiesForm(LoginRequiredMixin, View):
    """Handles entity tagging form display and submission."""

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, journal_entry_item_id):
        journal_entry_item = get_object_or_404(
            JournalEntryItem, pk=journal_entry_item_id
        )
        html = entity_helpers.render_entity_tag_form(journal_entry_item, None)
        return HttpResponse(html)

    def post(self, request, journal_entry_item_id):
        journal_entry_item = get_object_or_404(
            JournalEntryItem, pk=journal_entry_item_id
        )

        form = JournalEntryItemEntityForm(request.POST, instance=journal_entry_item)
        if form.is_valid():
            form.save()

        html = _render_full_page(preloaded_entity=form.cleaned_data["entity"])
        return HttpResponse(html)


class EntityGroupedBalancesView(LoginRequiredMixin, View):
    """Returns just the grouped balances section (for hide-zero toggle)."""

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request):
        hide_zero = request.GET.get("hide_zero", "1") != "0"
        grouped_balances = entity_services.get_grouped_entities_balances(
            hide_zero=hide_zero
        )
        html = entity_helpers.render_entity_grouped_balances_table(
            grouped_balances, hide_zero, history_html=""
        )
        return HttpResponse(html)


class TagEntitiesView(LoginRequiredMixin, View):
    """Main page for entity tagging (payables/receivables)."""

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request):
        hide_zero = request.GET.get("hide_zero", "1") != "0"
        html = _render_full_page(is_initial_load=True, hide_zero=hide_zero)
        return HttpResponse(html)
