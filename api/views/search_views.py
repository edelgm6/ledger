"""
Search views for HTTP orchestration.

Views handle HTTP requests/responses only, delegating business logic to
services and rendering to helpers.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.views import View

from api.forms import BulkAccountChangeForm, SearchFilterForm
from api.models import Account
from api.services import search_services
from api.services.transaction_services import TransactionFilterResult
from api.views import search_helpers


def _get_search_results_from_form(form):
    """Parse a SearchFilterForm and return matching transactions via service."""
    data = form.cleaned_data
    return search_services.search_transactions(
        description=data.get("description"),
        date_from=data.get("date_from"),
        date_to=data.get("date_to"),
        accounts=data.get("account") or None,
        transaction_types=data.get("transaction_type") or None,
        is_closed=True,
        related_accounts=data.get("related_account") or None,
    )


def _render_search_content_response(search_result, success_message=None):
    """Shared rendering for search results + bulk form."""
    table_html = search_helpers.render_search_results_table(
        transactions=search_result.transactions,
        count=search_result.count,
    )
    accounts = Account.objects.filter(is_closed=False).order_by("name")
    bulk_form_html = search_helpers.render_bulk_action_form(accounts=accounts)
    return search_helpers.render_search_content(
        table_html=table_html,
        bulk_form_html=bulk_form_html,
        success_message=success_message,
    )


class SearchView(LoginRequiredMixin, View):
    """Full page render with filter form + empty content."""
    login_url = "/login/"

    def get(self, request):
        filter_form_html = search_helpers.render_search_filter_form(
            get_url=reverse("search-content"),
        )
        context = {
            "filter_form": filter_form_html,
            "search_content": "",
        }
        html = render_to_string("api/views/search.html", context)
        return HttpResponse(html)


class SearchContentView(LoginRequiredMixin, View):
    """HTMX target: renders search results + bulk form from filter params."""

    def get(self, request):
        form = SearchFilterForm(request.GET)
        if form.is_valid():
            result = _get_search_results_from_form(form)
        else:
            result = TransactionFilterResult(transactions=[], count=0)

        html = _render_search_content_response(result)
        return HttpResponse(html)


class SearchBulkUpdateView(LoginRequiredMixin, View):
    """Handles preview and apply actions for bulk account changes."""

    def post(self, request):
        action = request.POST.get("action")

        # Re-derive transactions from filter params (prevents tampering)
        filter_form = SearchFilterForm(request.POST)
        if filter_form.is_valid():
            search_result = _get_search_results_from_form(filter_form)
        else:
            search_result = TransactionFilterResult(transactions=[], count=0)

        bulk_form = BulkAccountChangeForm(request.POST)
        if not bulk_form.is_valid():
            errors = bulk_form.errors.as_text()
            return HttpResponse(f'<div class="alert alert-danger mt-2">{errors}</div>')

        from_account = bulk_form.cleaned_data["from_account"]
        to_account = bulk_form.cleaned_data["to_account"]

        if action == "preview":
            preview_result = search_services.preview_bulk_account_change(
                transactions=search_result.transactions,
                from_account=from_account,
                to_account=to_account,
            )
            html = search_helpers.render_bulk_preview(
                affected_count=preview_result.affected_count,
                from_account=preview_result.from_account,
                to_account=preview_result.to_account,
            )
            return HttpResponse(html)

        elif action == "apply":
            update_result = search_services.apply_bulk_account_change(
                transactions=search_result.transactions,
                from_account_id=from_account.pk,
                to_account_id=to_account.pk,
            )

            if not update_result.success:
                return HttpResponse(
                    f'<div class="alert alert-danger">{update_result.error}</div>',
                    status=400,
                )

            # Re-query to show updated results
            search_result = _get_search_results_from_form(filter_form)
            html = _render_search_content_response(
                search_result,
                success_message=f"Updated {update_result.updated_count} journal entry items.",
            )
            return HttpResponse(html)

        return HttpResponse("Invalid action", status=400)
