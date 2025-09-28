from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views import View
from django.db.models import OuterRef, Subquery

from api import utils
from api.factories import TaxChargeFactory
from api.forms import TaxChargeFilterForm, TaxChargeForm
from api.models import TaxCharge, Account
from api.statement import IncomeStatement


class TaxChargeMixIn:
    def _get_taxable_income(self, end_date):
        first_day_of_month = date(end_date.year, end_date.month, 1)
        taxable_income = IncomeStatement(
            end_date, first_day_of_month
        ).get_taxable_income()
        return taxable_income

    def _add_tax_rate_and_charge(
        self, tax_charge, taxable_income=None, current_taxable_income=None
    ):
        if not taxable_income:
            taxable_income = self._get_taxable_income(end_date=tax_charge.date)
        tax_charge.taxable_income = taxable_income
        tax_charge.tax_rate = (
            None if taxable_income == 0 else tax_charge.amount / taxable_income
        )
        if current_taxable_income and tax_charge.tax_rate:
            tax_charge.current_tax = tax_charge.tax_rate * current_taxable_income

    def get_tax_filter_form_html(self):
        filter_template = "api/filter_forms/tax-charge-filter-form.html"
        html = render_to_string(filter_template, {"filter_form": TaxChargeFilterForm()})
        return html

    def get_tax_form_html(self, tax_charge=None, last_day_of_month=None):
        if tax_charge:
            form = TaxChargeForm(instance=tax_charge)
            last_day_of_month = tax_charge.date
        else:
            form = TaxChargeForm()

        last_day_of_month = (
            last_day_of_month
            if last_day_of_month
            else utils.get_last_day_of_last_month()
        )
        first_day_of_month = date(last_day_of_month.year, last_day_of_month.month, 1)
        income_statement = IncomeStatement(last_day_of_month, first_day_of_month)
        current_taxable_income = income_statement.get_taxable_income()

        tax_accounts = Account.objects.filter(sub_type=Account.SubType.TAX)
        for account in tax_accounts:
            if account.tax_rate:
                recommended_tax = account.tax_rate * current_taxable_income
            elif account.tax_amount:
                recommended_tax = account.tax_amount
            else:
                recommended_tax = None

            account.recommended_tax = recommended_tax

        context = {
            "form": form,
            "taxable_income": current_taxable_income,
            "tax_accounts": tax_accounts,
            "tax_charge": tax_charge,
        }
        form_template = "api/entry_forms/edit-tax-charge-form.html"
        form_html = render_to_string(form_template, context)
        return form_html

    def get_tax_table_html(self, tax_charges, end_date):
        tax_charges = tax_charges.select_related(
            "transaction", "transaction__account"
        ).order_by("date", "account")
        tax_dates = []
        taxable_income = None
        for tax_charge in tax_charges:
            # Limit the number of IncomeStatement objects we need to make
            if tax_charge.date not in tax_dates:
                taxable_income = self._get_taxable_income(tax_charge.date)
                tax_dates.append(tax_charge.date)
            self._add_tax_rate_and_charge(
                tax_charge=tax_charge, taxable_income=taxable_income
            )
            tax_charge.transaction_string = str(tax_charge.transaction)

        tax_charge_table_html = render_to_string(
            "api/tables/tax-table.html", {"tax_charges": tax_charges}
        )

        return tax_charge_table_html


class TaxChargeTableView(TaxChargeMixIn, LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, *args, **kwargs):
        form = TaxChargeFilterForm(request.GET)
        if form.is_valid():
            tax_charges = form.get_tax_charges()
            tax_table_charge_table_html = self.get_tax_table_html(
                tax_charges, end_date=form.cleaned_data["date_to"]
            )

            template = "api/content/taxes-content.html"
            context = {
                "tax_charge_table": tax_table_charge_table_html,
                "form": self.get_tax_form_html(),
            }
            html = render_to_string(template, context)

            return HttpResponse(html)


class TaxChargeFormView(TaxChargeMixIn, LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, pk=None, *args, **kwargs):
        if pk:
            tax_charge = get_object_or_404(TaxCharge, pk=pk)
        else:
            tax_charge = None

        form_html = self.get_tax_form_html(tax_charge=tax_charge)

        return HttpResponse(form_html)


# Loads full page
class TaxesView(TaxChargeMixIn, LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, *args, **kwargs):
        initial_end_date = utils.get_last_day_of_last_month()
        TaxChargeFactory.create_bulk_tax_charges(date=initial_end_date)

        six_months_ago = utils.get_last_days_of_month_tuples()[5][0]
        tax_charges = TaxCharge.objects.filter(
            date__gte=six_months_ago, date__lte=initial_end_date
        )

        context = {
            "tax_charge_table": self.get_tax_table_html(
                tax_charges=tax_charges, end_date=initial_end_date
            ),
            "form": self.get_tax_form_html(
                last_day_of_month=utils.get_last_day_of_last_month()
            ),
            "filter_form": self.get_tax_filter_form_html(),
        }
        template = "api/views/taxes.html"
        html = render_to_string(template, context)
        return HttpResponse(html)

    def post(self, request, pk=None, *args, **kwargs):
        form_class = TaxChargeForm
        if pk:
            tax_charge = get_object_or_404(TaxCharge, pk=pk)
            form = form_class(data=request.POST, instance=tax_charge)
        else:
            form = form_class(data=request.POST)

        if form.is_valid():
            tax_charge = form.save()
            tax_charges_form = TaxChargeFilterForm(request.POST)
            if tax_charges_form.is_valid():
                tax_charges = tax_charges_form.get_tax_charges()

            end_date = request.POST.get("date_to")
            context = {
                "tax_charge_table": self.get_tax_table_html(
                    tax_charges=tax_charges, end_date=end_date
                ),
                "form": self.get_tax_form_html(),
            }
            template = "api/content/taxes-content.html"
            html = render_to_string(template, context)
            return HttpResponse(html)
        else:
            print(form.errors)
