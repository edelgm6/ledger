"""
Views for the utility-bill Settings sections.

Two surfaces, both loaded as HTML fragments into the Settings shell:
- Bill Rules: config CRUD over UtilityBillRule (mirrors SettingsView/Accounts).
- Utility Bills: a read-only monitor of ingested bills with "Poll now" and a
  per-bill "Retry" action.

Views parse requests, call services for business logic, and call helpers for
rendering. No database writes and no HTML building here.
"""

from typing import Optional

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from api.forms import UtilityBillRuleForm
from api.models import UtilityBillRule
from api.services import bill_rule_services, bill_services
from api.views import bill_settings_helpers


class BillRulesView(LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def _render_content(
        self,
        rule: Optional[UtilityBillRule] = None,
        change: Optional[str] = None,
        error: Optional[str] = None,
        form: Optional[UtilityBillRuleForm] = None,
        selected_id: Optional[int] = None,
    ) -> str:
        """Builds the swappable Bill Rules fragment (header + table + form)."""
        accounts, entities = bill_rule_services.get_bill_rule_form_options()
        rule_form_html = bill_settings_helpers.render_bill_rule_form(
            accounts=accounts,
            entities=entities,
            rule=rule,
            change=change,
            error=error,
            form=form,
        )
        rules = bill_rule_services.get_bill_rules()
        return bill_settings_helpers.render_bill_rules_content(
            rules=rules,
            rule_form_html=rule_form_html,
            selected_id=selected_id,
        )

    def get(self, request):
        return HttpResponse(self._render_content())

    def post(self, request, rule_id=None):
        action = request.POST.get("action")

        if action == "clear":
            return HttpResponse(self._render_content())

        if action == "delete":
            result = bill_rule_services.delete_bill_rule(rule_id)
            if result.success:
                return HttpResponse(self._render_content(change="delete"))
            return HttpResponse(
                self._render_content(
                    rule=result.rule,
                    error=result.error,
                    selected_id=result.rule.id if result.rule else None,
                )
            )

        if rule_id:
            rule = get_object_or_404(UtilityBillRule, pk=rule_id)
            form = UtilityBillRuleForm(request.POST, instance=rule)
            change = "update"
        else:
            rule = None
            form = UtilityBillRuleForm(request.POST)
            change = "create"

        if not form.is_valid():
            return HttpResponse(
                self._render_content(
                    rule=rule,
                    form=form,
                    selected_id=rule.id if rule else None,
                )
            )

        result = bill_rule_services.save_bill_rule(form.cleaned_data, instance=rule)
        if not result.success:
            return HttpResponse(
                self._render_content(
                    rule=rule,
                    form=form,
                    error=result.error,
                    selected_id=rule.id if rule else None,
                )
            )

        return HttpResponse(
            self._render_content(
                rule=result.rule,
                change=change,
                selected_id=result.rule.id,
            )
        )


class BillRuleFormView(LoginRequiredMixin, View):
    """Loads a rule (or a blank create form) into the edit form.

    Used on table row clicks (existing rule) and the New Rule button (no
    rule_id -> blank form).
    """

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, rule_id=None):
        rule = (
            get_object_or_404(UtilityBillRule, pk=rule_id) if rule_id else None
        )
        accounts, entities = bill_rule_services.get_bill_rule_form_options()
        form_html = bill_settings_helpers.render_bill_rule_form(
            accounts=accounts,
            entities=entities,
            rule=rule,
        )
        return HttpResponse(form_html)


class BillsView(LoginRequiredMixin, View):
    """Read-only monitor of ingested bills with Poll-now and per-bill Retry."""

    login_url = "/login/"
    redirect_field_name = "next"

    def _render_content(self, message: Optional[str] = None) -> str:
        bills = bill_services.get_bills()
        return bill_settings_helpers.render_bills_content(bills, message=message)

    def get(self, request):
        return HttpResponse(self._render_content())

    def post(self, request):
        action = request.POST.get("action")
        message = None

        if action == "poll":
            # Synchronous on purpose: the 7-day search window + source_message_id
            # dedupe keep a poll cheap (only genuinely-new emails hit Gemini), so
            # it stays well under the request timeout without needing Celery.
            result = bill_services.poll_bill_emails()
            message = (
                f"Poll complete — fetched {result.fetched}, new {result.new}, "
                f"parsed {result.parsed}, unresolved {result.unresolved}, "
                f"failed {result.failed}."
            )
        elif action == "retry":
            bill_id = request.POST.get("bill_id")
            bill = bill_services.retry_bill(int(bill_id)) if bill_id else None
            message = (
                f"Retried bill — now {bill.get_status_display()}."
                if bill
                else "Could not retry that bill."
            )

        return HttpResponse(self._render_content(message=message))
