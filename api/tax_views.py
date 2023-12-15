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

class TaxTableMixIn:

    def get_tax_form_html(self, last_day_of_month):
        first_day_of_month = date(last_day_of_month.year, last_day_of_month.month, 1)
        income_statement = IncomeStatement(last_day_of_month, first_day_of_month)
        latest_federal_tax_charge = TaxCharge.objects.filter(type=TaxCharge.Type.FEDERAL).order_by('-date').first()
        latest_state_tax_charge = TaxCharge.objects.filter(type=TaxCharge.Type.STATE).order_by('-date').first()
        latest_property_tax_charge = TaxCharge.objects.filter(type=TaxCharge.Type.PROPERTY).order_by('-date').first()

        current_taxable_income = income_statement.get_taxable_income()

        for tax_charge in [latest_federal_tax_charge,latest_state_tax_charge]:
            if tax_charge:
                last_day_of_month = tax_charge.date
                first_day_of_month = date(last_day_of_month.year, last_day_of_month.month, 1)
                taxable_income = IncomeStatement(tax_charge.date, first_day_of_month).get_taxable_income()
                tax_charge.tax_rate = None if taxable_income == 0 else tax_charge.amount / taxable_income
                tax_charge.current_tax = tax_charge.tax_rate * current_taxable_income

        form_template = 'api/entry_forms/edit-tax-charge-form.html'
        context = {
            'form': TaxChargeForm(),
            'taxable_income': current_taxable_income,
            'latest_federal_tax_charge': latest_federal_tax_charge,
            'latest_state_tax_charge': latest_state_tax_charge,
            'latest_property_tax_charge': latest_property_tax_charge
        }

        form_html = render_to_string(form_template, context)
        return form_html

    def get_tax_table_html(self, tax_charges):

        tax_charges = tax_charges.order_by('date','type')
        for tax_charge in tax_charges:
            last_day_of_month = tax_charge.date
            first_day_of_month = date(last_day_of_month.year, last_day_of_month.month, 1)
            taxable_income = IncomeStatement(tax_charge.date, first_day_of_month).get_taxable_income()
            tax_charge.taxable_income = taxable_income
            tax_charge.tax_rate = None if taxable_income == 0 else tax_charge.amount / taxable_income

        tax_charge_table_html = render_to_string(
            'api/tables/tax-table.html',
            {'tax_charges': tax_charges}
        )

        return tax_charge_table_html

class TaxChargeTableView(TaxTableMixIn, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, *args, **kwargs):
        form = TaxChargeFilterForm(request.GET)
        if form.is_valid():
            tax_charges = form.get_tax_charges()
            tax_table_charge_table_html = self.get_tax_table_html(tax_charges)

            template = 'api/components/taxes-content.html'
            form_template = 'api/entry_forms/edit-tax-charge-form.html'
            context = {
                'tax_charge_table': tax_table_charge_table_html,
                'form': render_to_string(form_template, {'form': TaxChargeForm()}),
            }

            return render(request, template, context)

class TaxChargeFormView(TaxTableMixIn, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    form_class = TaxChargeForm
    form_template = 'api/entry_forms/edit-tax-charge-form.html'

    def get(self, request, pk=None, *args, **kwargs):
        if pk:
            tax_charge = get_object_or_404(TaxCharge, pk=pk)
            form = self.form_class(instance=tax_charge)
        else:
            tax_charge = None
            form = self.form_class()

        context = {
            'form': form,
            'tax_charge': tax_charge
        }

        return render(request, self.form_template, context)

    def post(self, request, pk=None, *args, **kwargs):
        if pk:
            tax_charge = get_object_or_404(TaxCharge, pk=pk)
            form = self.form_class(data=request.POST, instance=tax_charge)
        else:
            form = self.form_class(data=request.POST)

        if form.is_valid():
            tax_charge = form.save()
            tax_charges_form = TaxChargeFilterForm(request.POST)
            if tax_charges_form.is_valid():
                tax_charges = tax_charges_form.get_tax_charges()

            context = {
                'tax_charge_table': self.get_tax_table_html(tax_charges),
                'form': render_to_string(self.form_template, {'form': form})
            }
            form_template = 'api/components/taxes-content.html'
            return render(request, form_template, context)

# Loads full page
class TaxesView(TaxTableMixIn, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

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

    def get(self, request, *args, **kwargs):

        tax_charges = TaxCharge.objects.filter(date__gte='2023-01-31',date__lte=self._get_last_day_of_last_month())
        tax_charge_table = self.get_tax_table_html(tax_charges)
        template = 'api/views/taxes.html'
        filter_template = 'api/filter_forms/tax-charge-filter-form.html'
        context = {
            'tax_charge_table': tax_charge_table,
            'form': self.get_tax_form_html(self._get_last_day_of_last_month()),
            'filter_form': render_to_string(filter_template, {'filter_form': TaxChargeFilterForm()})
        }

        return render(request, template, context)
