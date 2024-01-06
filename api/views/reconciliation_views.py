from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.forms import modelformset_factory
from api.models import  Reconciliation
from api.forms import ReconciliationFilterForm, ReconciliationForm
from api.statement import BalanceSheet
from api.factories import ReconciliationFactory
from api import utils

class ReconciliationTableMixin:

    def _get_current_balance(self, reconciliation):
        balance_sheet = BalanceSheet(reconciliation.date)
        balance = balance_sheet.get_balance(reconciliation.account)
        return balance

    def get_reconciliation_html(self, reconciliations):
        reconciliations = reconciliations.order_by('account')

        for reconciliation in reconciliations:
            reconciliation.current_balance = self._get_current_balance(reconciliation)

        ReconciliationFormset = modelformset_factory(Reconciliation, ReconciliationForm, extra=0)

        formset = ReconciliationFormset(queryset=reconciliations)
        zipped_reconciliations = zip(reconciliations, formset)
        zipped_reconciliations_list = list(zipped_reconciliations)

        # Calculate the split index. Add 1 if the number of items is odd.
        split_index = (len(zipped_reconciliations_list) + 1) // 2  # integer division

        # Split the list into two parts, giving the left side the extra item if count is odd
        left_reconciliations = zipped_reconciliations_list[:split_index]
        right_reconciliations = zipped_reconciliations_list[split_index:]

        template = 'api/tables/reconciliation-table.html'
        return render_to_string(
            template,
            {
                # 'zipped_reconciliations': zipped_reconciliations,
                'left_reconciliations': left_reconciliations,
                'right_reconciliations': right_reconciliations,
                'formset': formset
            }
        )

# Loads reconciliation table
class ReconciliationTableView(ReconciliationTableMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, *args, **kwargs):

        form = ReconciliationFilterForm(request.GET)
        if form.is_valid():
            ReconciliationFactory.create_bulk_reconciliations(date=form.cleaned_data['date'])
            reconciliations = form.get_reconciliations()

            reconciliations_table = self.get_reconciliation_html(reconciliations)
            return HttpResponse(reconciliations_table)

# Loads full page
class ReconciliationView(ReconciliationTableMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, *args, **kwargs):

        template = 'api/views/reconciliation.html'
        initial_date = utils.get_last_day_of_last_month()
        ReconciliationFactory.create_bulk_reconciliations(date=initial_date)

        reconciliations = Reconciliation.objects.filter(date=initial_date)
        reconciliation_table = self.get_reconciliation_html(reconciliations)
        context = {
            'reconciliation_table': reconciliation_table,
            'filter_form': render_to_string(
                'api/filter_forms/reconciliation-filter-form.html',
                {'filter_form': ReconciliationFilterForm()}
            )
        }

        return render(request, template, context)

    def post(self, request):
        if request.POST.get('plug'):
            reconciliation = get_object_or_404(Reconciliation, pk=request.POST.get('plug'))
            reconciliation.plug_investment_change()
        else:
            ReconciliationFormset = modelformset_factory(Reconciliation, ReconciliationForm, extra=0)
            formset = ReconciliationFormset(request.POST)

            if formset.is_valid():
                reconciliations = formset.save()
            print(formset.errors)

        filter_form = ReconciliationFilterForm(request.POST)
        if filter_form.is_valid():
            reconciliations = filter_form.get_reconciliations()

        reconciliation_table = self.get_reconciliation_html(reconciliations)

        return HttpResponse(reconciliation_table)