"""
Settings views for HTTP orchestration.

Views parse requests, call services for business logic, and call helpers for
rendering. They contain no database writes and no HTML building. The Settings
page hosts user-facing CRUD for configuration models, starting with Account.
"""

from typing import Optional

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views import View

from api.forms import AccountForm
from api.models import Account
from api.services import account_services
from api.views import settings_helpers
from api.views.page_utils import render_full_page


class SettingsView(LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    view_template = "api/views/settings.html"

    def _render_content(
        self,
        account: Optional[Account] = None,
        change: Optional[str] = None,
        error: Optional[str] = None,
        form: Optional[AccountForm] = None,
        selected_id: Optional[int] = None,
    ) -> str:
        """Builds the swappable right-pane fragment (header + table + form)."""
        entities, csv_profiles = account_services.get_account_form_options()
        account_form_html = settings_helpers.render_account_form(
            entities=entities,
            csv_profiles=csv_profiles,
            account=account,
            change=change,
            error=error,
            form=form,
        )
        accounts = account_services.get_accounts()
        return settings_helpers.render_settings_content(
            accounts=accounts,
            account_form_html=account_form_html,
            selected_id=selected_id,
        )

    def get(self, request):
        content_html = self._render_content()
        html = render_to_string(self.view_template, {"content": content_html})
        return render_full_page(request, html)

    def post(self, request, account_id=None):
        action = request.POST.get("action")

        if action == "clear":
            return HttpResponse(self._render_content())

        if action == "delete":
            result = account_services.delete_account(account_id)
            if result.success:
                return HttpResponse(self._render_content(change="delete"))
            # Re-render the still-existing account with the friendly error.
            return HttpResponse(
                self._render_content(
                    account=result.account,
                    error=result.error,
                    selected_id=result.account.id if result.account else None,
                )
            )

        # Create or update
        if account_id:
            account = get_object_or_404(Account, pk=account_id)
            form = AccountForm(request.POST, instance=account)
            change = "update"
        else:
            account = None
            form = AccountForm(request.POST)
            change = "create"

        if not form.is_valid():
            return HttpResponse(
                self._render_content(
                    account=account,
                    form=form,
                    selected_id=account.id if account else None,
                )
            )

        result = account_services.save_account(form.cleaned_data, instance=account)
        if not result.success:
            return HttpResponse(
                self._render_content(
                    account=account,
                    form=form,
                    error=result.error,
                    selected_id=account.id if account else None,
                )
            )

        return HttpResponse(
            self._render_content(
                account=result.account,
                change=change,
                selected_id=result.account.id,
            )
        )


class AccountFormView(LoginRequiredMixin, View):
    """Loads an account (or a blank create form) into the edit form.

    Used on table row clicks (existing account) and the New Account button
    (no account_id -> blank form).
    """

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, account_id=None):
        account = get_object_or_404(Account, pk=account_id) if account_id else None
        entities, csv_profiles = account_services.get_account_form_options()
        form_html = settings_helpers.render_account_form(
            entities=entities,
            csv_profiles=csv_profiles,
            account=account,
        )
        return HttpResponse(form_html)
