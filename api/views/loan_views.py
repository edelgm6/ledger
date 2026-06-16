"""
Views for the Loans Settings section.

Loaded as HTML fragments into the Settings shell:
- Loans: config CRUD over Loan (mirrors BillRulesView/Accounts).
- Loan schedule: view + inline edit of a loan's amortization rows.

Views parse requests, call services for business logic, and call helpers for
rendering. No database writes and no HTML building here.
"""

from decimal import Decimal, InvalidOperation
from typing import Optional

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from api.forms import LoanForm
from api.models import Loan, LoanPayment
from api.services import loan_services
from api.views import loan_helpers


class LoanSettingsView(LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def _render_content(
        self,
        loan: Optional[Loan] = None,
        change: Optional[str] = None,
        error: Optional[str] = None,
        form: Optional[LoanForm] = None,
        selected_id: Optional[int] = None,
    ) -> str:
        """Builds the swappable Loans fragment (header + table + form)."""
        (
            liability_accounts,
            expense_accounts,
            payment_accounts,
            entities,
        ) = loan_services.get_loan_form_options()
        loan_form_html = loan_helpers.render_loan_form(
            liability_accounts=liability_accounts,
            expense_accounts=expense_accounts,
            payment_accounts=payment_accounts,
            entities=entities,
            loan=loan,
            change=change,
            error=error,
            form=form,
        )
        loans = loan_services.get_loans()
        return loan_helpers.render_loans_content(
            loans=loans,
            loan_form_html=loan_form_html,
            selected_id=selected_id,
        )

    def get(self, request):
        return HttpResponse(self._render_content())

    def post(self, request, loan_id=None):
        action = request.POST.get("action")

        if action == "clear":
            return HttpResponse(self._render_content())

        if action == "delete":
            result = loan_services.delete_loan(loan_id)
            if result.success:
                return HttpResponse(self._render_content(change="delete"))
            return HttpResponse(
                self._render_content(
                    loan=result.loan,
                    error=result.error,
                    selected_id=result.loan.id if result.loan else None,
                )
            )

        if loan_id:
            loan = get_object_or_404(Loan, pk=loan_id)
            form = LoanForm(request.POST, instance=loan)
            change = "update"
        else:
            loan = None
            form = LoanForm(request.POST)
            change = "create"

        if not form.is_valid():
            return HttpResponse(
                self._render_content(
                    loan=loan,
                    form=form,
                    selected_id=loan.id if loan else None,
                )
            )

        result = loan_services.save_loan(form.cleaned_data, instance=loan)
        if not result.success:
            return HttpResponse(
                self._render_content(
                    loan=loan,
                    form=form,
                    error=result.error,
                    selected_id=loan.id if loan else None,
                )
            )

        return HttpResponse(
            self._render_content(
                loan=result.loan,
                change=change,
                selected_id=result.loan.id,
            )
        )


class LoanFormView(LoginRequiredMixin, View):
    """Loads a loan (or a blank create form) into the edit form.

    Used on table row clicks (existing loan) and the New Loan button (no
    loan_id -> blank form).
    """

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, loan_id=None):
        loan = get_object_or_404(Loan, pk=loan_id) if loan_id else None
        (
            liability_accounts,
            expense_accounts,
            payment_accounts,
            entities,
        ) = loan_services.get_loan_form_options()
        form_html = loan_helpers.render_loan_form(
            liability_accounts=liability_accounts,
            expense_accounts=expense_accounts,
            payment_accounts=payment_accounts,
            entities=entities,
            loan=loan,
        )
        return HttpResponse(form_html)


class LoanScheduleView(LoginRequiredMixin, View):
    """Renders a loan's amortization schedule (GET) and applies an inline
    principal/interest edit to one row (POST), re-amortizing the rest."""

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, loan_id):
        loan = get_object_or_404(Loan, pk=loan_id)
        rows = loan_services.get_schedule(loan_id)
        return HttpResponse(loan_helpers.render_loan_schedule(loan, rows))

    @staticmethod
    def _decimal(raw):
        try:
            return Decimal(str(raw).replace(",", "").replace("$", ""))
        except (InvalidOperation, ValueError):
            return None

    def post(self, request, row_id):
        row = get_object_or_404(LoanPayment, pk=row_id)
        action = request.POST.get("action")
        message = None

        if action == "clear_balance":
            result = loan_services.clear_row_anchor(row_id)
            message = "Balance anchor cleared." if result.success else result.error
        else:
            # Every save anchors: it records the split and pins the balance
            # baseline as of this row, then re-amortizes forward.
            principal = self._decimal(request.POST.get("principal_amount", ""))
            interest = self._decimal(request.POST.get("interest_amount", ""))
            balance = self._decimal(request.POST.get("balance_override", ""))
            if principal is None or interest is None or balance is None:
                message = "Enter valid principal, interest, and balance amounts."
            else:
                result = loan_services.save_schedule_row(
                    row_id, principal, interest, balance
                )
                message = (
                    "Row saved — balance anchored and schedule re-amortized."
                    if result.success
                    else result.error
                )

        loan = row.loan
        loan.refresh_from_db()
        rows = loan_services.get_schedule(loan.id)
        return HttpResponse(loan_helpers.render_loan_schedule(loan, rows, message=message))
