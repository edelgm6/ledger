"""
Statement views for income statement, balance sheet, and cash flow statement.

Views handle HTTP orchestration only. Business logic is in statement_services.py,
and rendering is in statement_helpers.py.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View

from api import utils
from api.forms import FromToDateForm
from api.services import statement_services
from api.statement import BalanceSheet, IncomeStatement
from api.views import statement_helpers
from api.views.page_utils import render_full_page


class StatementDetailView(LoginRequiredMixin, View):
    """View for account drill-down in statements."""

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, account_id, *args, **kwargs):
        from_date = request.GET.get("from_date")
        to_date = request.GET.get("to_date")

        # Get detail data via service
        detail_data = statement_services.get_statement_detail_items(
            account_id=account_id,
            from_date=from_date,
            to_date=to_date,
        )

        # Render via helper
        html = statement_helpers.render_statement_detail_table(detail_data)
        return HttpResponse(html)


class StatementEntityDetailView(LoginRequiredMixin, View):
    """View for entity drill-down in the entity-grouped income statement."""

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, *args, **kwargs):
        entity_id = request.GET.get("entity_id") or None
        account_type = request.GET.get("account_type")
        from_date = request.GET.get("from_date")
        to_date = request.GET.get("to_date")

        detail_data = statement_services.get_statement_detail_items_by_entity(
            entity_id=entity_id,
            account_type=account_type,
            from_date=from_date,
            to_date=to_date,
        )

        html = statement_helpers.render_statement_detail_table(detail_data)
        return HttpResponse(html)


class StatementView(LoginRequiredMixin, View):
    """Main view for financial statements."""

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, statement_type, *args, **kwargs):
        # 1. Parse form or use defaults
        form = FromToDateForm(request.GET)
        if form.is_valid():
            from_date = form.cleaned_data["date_from"]
            to_date = form.cleaned_data["date_to"]
        else:
            from_date, to_date = self._get_default_dates()

        group_by = request.GET.get("group_by", "account")

        # 2. Route to statement type handler
        if statement_type == "income":
            if group_by == "entity":
                statement_html = self._render_income_statement_by_entity(
                    from_date, to_date
                )
            else:
                statement_html = self._render_income_statement(from_date, to_date)
            title = "Income Statement"
        elif statement_type == "balance":
            statement_html = self._render_balance_sheet(to_date)
            title = "Balance Sheet"
        elif statement_type == "cash":
            statement_html = self._render_cash_flow(from_date, to_date)
            title = "Cash Flow Statement"

        # 3. Render filter form via helper
        filter_form_html = statement_helpers.render_statement_filter_form(
            statement_type=statement_type,
            from_date=from_date,
            to_date=to_date,
            group_by=group_by,
        )

        # 4. Return combined response
        context = {
            "statement": statement_html,
            "filter_form": filter_form_html,
            "title": title,
        }
        template = "api/views/statement.html"
        html = render_to_string(template, context)
        return render_full_page(request, html)

    def _get_default_dates(self):
        """Get last month date range."""
        last_month_tuple = utils.get_last_days_of_month_tuples()[0]
        last_day = last_month_tuple[0]
        first_day = utils.get_first_day_of_month_from_date(last_day)
        return first_day, last_day

    def _render_income_statement(self, from_date, to_date):
        """Render income statement using services and helpers."""
        income_statement = IncomeStatement(end_date=to_date, start_date=from_date)
        summary = statement_services.build_statement_summary(income_statement)

        return statement_helpers.render_income_statement(
            summary=summary,
            tax_rate=income_statement.get_tax_rate(),
            savings_rate=income_statement.get_savings_rate(),
            from_date=from_date,
            to_date=to_date,
        )

    def _render_income_statement_by_entity(self, from_date, to_date):
        """Render income statement grouped by entity using services and helpers."""
        income_statement = IncomeStatement(end_date=to_date, start_date=from_date)
        summary = statement_services.build_entity_income_summary(income_statement)

        return statement_helpers.render_income_statement_by_entity(
            summary=summary,
            tax_rate=income_statement.get_tax_rate(),
            savings_rate=income_statement.get_savings_rate(),
            from_date=from_date,
            to_date=to_date,
        )

    def _render_balance_sheet(self, to_date):
        """Render balance sheet using services and helpers."""
        balance_sheet = BalanceSheet(end_date=to_date)
        summary = statement_services.build_statement_summary(balance_sheet)
        unbalanced = statement_services.find_unbalanced_journal_entries()

        return statement_helpers.render_balance_sheet(
            summary=summary,
            cash_percent_assets=balance_sheet.get_cash_percent_assets(),
            debt_to_equity_ratio=balance_sheet.get_debt_to_equity(),
            liquid_percent_assets=balance_sheet.get_liquid_assets_percent(),
            unbalanced_entries=unbalanced.entries,
        )

    def _render_cash_flow(self, from_date, to_date):
        """Render cash flow statement using services and helpers."""
        metrics = statement_services.calculate_cash_flow_metrics(from_date, to_date)
        return statement_helpers.render_cash_flow_statement(metrics)
