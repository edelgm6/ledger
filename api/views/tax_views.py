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

        tax_charges = TaxCharge.objects.filter(amount__gt=0).order_by(
            "account_id", "-date"
        )

        latest_by_account = {}
        for tax_charge in tax_charges:
            if tax_charge.account not in latest_by_account:
                latest_by_account[tax_charge.account] = tax_charge

        # now you have one TaxCharge (latest) per account
        latest_taxcharges = [value for value in latest_by_account.values()]
        print(latest_taxcharges)

        # Step 1: Define a subquery that, for a given Account,
        # finds that account’s most recent TaxCharge (with amount > 0).
        # latest_taxcharge_subquery = (
        #     TaxCharge.objects
        #     # filter to just rows for *this account* (OuterRef refers to the Account we're comparing against)
        #     .filter(account=OuterRef("pk"), amount__gt=0)
        #     # order newest first (so the first row is the latest one)
        #     .order_by("-date")
        #     # we don’t want the whole row, just the primary key of the TaxCharge
        #     .values("pk")[:1]  # slice = "take only the first row"
        # )

        # # Step 2: Use that subquery to filter the actual TaxCharge table
        # # We say "give me TaxCharges where the pk is equal to the subquery result"
        # latest_taxcharges = TaxCharge.objects.filter(
        #     pk__in=Subquery(latest_taxcharge_subquery)
        # )
        # print(latest_taxcharges)
        # Get latest charge that has a positive value to account for auto-created
        # tax charges
        # This charge will be used to fill out the recommended charges table
        # latest_federal_tax_charge = (
        #     TaxCharge.objects.filter(type=TaxCharge.Type.FEDERAL, amount__gt=0)
        #     .order_by("-date")
        #     .first()
        # )
        # latest_state_tax_charge = (
        #     TaxCharge.objects.filter(type=TaxCharge.Type.STATE, amount__gt=0)
        #     .order_by("-date")
        #     .first()
        # )
        # latest_property_tax_charge = (
        #     TaxCharge.objects.filter(type=TaxCharge.Type.PROPERTY, amount__gt=0)
        #     .order_by("-date")
        #     .first()
        # )

        current_taxable_income = income_statement.get_taxable_income()
        # for latest_tax_charge in [latest_federal_tax_charge, latest_state_tax_charge]:
        #     self._add_tax_rate_and_charge(
        #         tax_charge=latest_tax_charge,
        #         taxable_income=self._get_taxable_income(latest_tax_charge.date),
        #         current_taxable_income=current_taxable_income,
        #     )

        for latest_taxcharge in latest_taxcharges:
            print("****wtf*****")
            print(latest_taxcharge)
            print(latest_taxcharge.account)
            print("****wtf*****")
            if (
                latest_taxcharge.account.special_type
                is not Account.SpecialType.PROPERTY_TAXES
            ):
                self._add_tax_rate_and_charge(
                    tax_charge=latest_taxcharge,
                    taxable_income=self._get_taxable_income(latest_taxcharge.date),
                    current_taxable_income=current_taxable_income,
                )

        context = {
            "form": form,
            "taxable_income": current_taxable_income,
            "latest_taxcharges": latest_taxcharges,
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
