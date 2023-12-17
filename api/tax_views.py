import calendar
from datetime import date, datetime
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from api.models import  TaxCharge
from api.forms import TaxChargeFilterForm, TaxChargeForm
from api.statement import IncomeStatement

class TaxChargeMixIn:

    def _get_last_day_of_last_month(self):
        current_date = datetime.now()

        # Calculate the year and month for the previous month
        year = current_date.year
        month = current_date.month - 1

        # If it's currently January, adjust to December of the previous year
        if month == 0:
            month = 12
            year -= 1

        # Get the last day of the previous month
        _, last_day = calendar.monthrange(year, month)
        last_day_date = date(year, month, last_day)

        return last_day_date

    def _add_tax_rate_and_charge(self, tax_charge, current_taxable_income=None):
        last_day_of_month = tax_charge.date
        first_day_of_month = date(last_day_of_month.year, last_day_of_month.month, 1)
        taxable_income = IncomeStatement(tax_charge.date, first_day_of_month).get_taxable_income()
        tax_charge.taxable_income = taxable_income
        tax_charge.tax_rate = None if taxable_income == 0 else tax_charge.amount / taxable_income
        if current_taxable_income:
            tax_charge.current_tax = tax_charge.tax_rate * current_taxable_income

    def get_tax_filter_form_html(self):
        filter_template = 'api/filter_forms/tax-charge-filter-form.html'
        html = render_to_string(filter_template, {'filter_form': TaxChargeFilterForm()})
        return html

    def get_tax_form_html(self, tax_charge=None, last_day_of_month=None):
        if tax_charge:
            form = TaxChargeForm(instance=tax_charge)
            last_day_of_month = tax_charge.date
        else:
            form = TaxChargeForm()

        last_day_of_month = last_day_of_month if last_day_of_month else self._get_last_day_of_last_month()
        first_day_of_month = date(last_day_of_month.year, last_day_of_month.month, 1)
        income_statement = IncomeStatement(last_day_of_month, first_day_of_month)
        latest_federal_tax_charge = TaxCharge.objects.filter(type=TaxCharge.Type.FEDERAL).order_by('-date').first()
        latest_state_tax_charge = TaxCharge.objects.filter(type=TaxCharge.Type.STATE).order_by('-date').first()
        latest_property_tax_charge = TaxCharge.objects.filter(type=TaxCharge.Type.PROPERTY).order_by('-date').first()

        current_taxable_income = income_statement.get_taxable_income()

        for latest_tax_charge in [latest_federal_tax_charge,latest_state_tax_charge]:
            if latest_tax_charge:
                self._add_tax_rate_and_charge(latest_tax_charge, current_taxable_income)

        context = {
            'form': form,
            'taxable_income': current_taxable_income,
            'latest_federal_tax_charge': latest_federal_tax_charge,
            'latest_state_tax_charge': latest_state_tax_charge,
            'latest_property_tax_charge': latest_property_tax_charge,
            'tax_charge': tax_charge
        }
        form_template = 'api/entry_forms/edit-tax-charge-form.html'
        form_html = render_to_string(form_template, context)
        return form_html

    def get_tax_table_html(self, tax_charges):

        tax_charges = tax_charges.order_by('date','type')
        for tax_charge in tax_charges:
            self._add_tax_rate_and_charge(tax_charge)

        tax_charge_table_html = render_to_string(
            'api/tables/tax-table.html',
            {'tax_charges': tax_charges}
        )

        return tax_charge_table_html

class TaxChargeTableView(TaxChargeMixIn, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, *args, **kwargs):
        form = TaxChargeFilterForm(request.GET)
        if form.is_valid():
            tax_charges = form.get_tax_charges()
            tax_table_charge_table_html = self.get_tax_table_html(tax_charges)

            template = 'api/components/taxes-content.html'
            context = {
                'tax_charge_table': tax_table_charge_table_html,
                'form': self.get_tax_form_html(),
            }
            html = render_to_string(template, context)

            return HttpResponse(html)

class TaxChargeFormView(TaxChargeMixIn, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, pk=None, *args, **kwargs):
        if pk:
            tax_charge = get_object_or_404(TaxCharge, pk=pk)
        else:
            tax_charge = None

        form_html = self.get_tax_form_html(tax_charge=tax_charge)

        return HttpResponse(form_html)

# Loads full page
class TaxesView(TaxChargeMixIn, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, *args, **kwargs):

        tax_charges = TaxCharge.objects.filter(date__gte='2023-01-31',date__lte=self._get_last_day_of_last_month())

        context = {
            'tax_charge_table': self.get_tax_table_html(tax_charges),
            'form': self.get_tax_form_html(last_day_of_month=self._get_last_day_of_last_month()),
            'filter_form': self.get_tax_filter_form_html
        }
        template = 'api/views/taxes.html'
        html = render_to_string(template, context)

        template = 'api/views/taxes.html'
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

            context = {
                'tax_charge_table': self.get_tax_table_html(tax_charges),
                'form': self.get_tax_form_html()
            }
            template = 'api/components/taxes-content.html'
            html = render_to_string(template, context)
            return HttpResponse(html)
