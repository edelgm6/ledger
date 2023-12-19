from django.http import HttpResponse
from django.template.loader import render_to_string
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from api.models import Amortization, Transaction, Account
from api.forms import AmortizationForm, DateForm

class AmortizationTableMixin:
    def get_amortization_table_html(self):
        amortizations = Amortization.objects.select_related('accrued_transaction').filter(is_closed=False)
        for amortization in amortizations:
            amortization.remaining_balance = amortization.get_remaining_balance()
            amortization.remaining_periods = amortization.get_remaining_periods()
        return render_to_string('api/tables/amortization-table.html',{'amortizations': amortizations})

    def get_unattached_prepaids_table_html(self):
        prepaid_table_template = 'api/tables/unattached-prepaids.html'
        unattached_transactions = Transaction.objects.filter(
            journal_entry__journal_entry_items__account__special_type=Account.SpecialType.PREPAID_EXPENSES,
            amortization__isnull=True
        ).exclude(
            accrued_amortizations__isnull=False
        )
        return render_to_string(prepaid_table_template,{'transactions': unattached_transactions})

    def get_amortization_form_html(self, transaction=None):
        form = AmortizationForm()
        if transaction:
            form.initial['accrued_transaction'] = transaction
        form_template = 'api/entry_forms/amortization-form.html'
        return render_to_string(form_template,{'form': form})

    def get_amortize_form_html(self, amortization):
        form_template = 'api/entry_forms/amortize-form.html'
        transactions = amortization.get_related_transactions()
        context = {
            'transactions': transactions,
            'amortization': amortization,
            'date_form': DateForm()
        }
        return render_to_string(form_template, context)

class AmortizeFormView(AmortizationTableMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, amortization_id):
        amortization = get_object_or_404(Amortization, pk=amortization_id)
        amortize_form_html = self.get_amortize_form_html(amortization)
        return HttpResponse(amortize_form_html)

    def post(self, request, amortization_id):
        amortization = get_object_or_404(Amortization, pk=amortization_id)
        form = DateForm(request.POST)
        if form.is_valid():
            amortization.amortize(form.cleaned_data['date'])

            context = {
                'table': self.get_amortization_table_html(),
                'amortization_form': self.get_amortize_form_html(amortization)
            }

            amortizations_content_template = 'api/components/amortizations-content.html'
            html = render_to_string(amortizations_content_template, context)
            return HttpResponse(html)

class AmortizationFormView(AmortizationTableMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, transaction_id):
        transaction = get_object_or_404(Transaction, pk=transaction_id)
        amortization_form_html = self.get_amortization_form_html(transaction)
        return HttpResponse(amortization_form_html)

class AmortizationView(AmortizationTableMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    amortizations_content_template = 'api/components/amortizations-content.html'
    unattached_transactions_content = 'api/components/unattached-transactions-content.html'
    amortizations_content = 'api/components/amortizations-content.html'

    def get(self, request, *args, **kwargs):

        # create amortizations
        unattached_transactions_html = self.get_unattached_prepaids_table_html()
        amortization_form_html = self.get_amortization_form_html()

        # amortize
        amortizations_table_html = self.get_amortization_table_html()

        context = {
            'unattached_transactions': render_to_string(
                self.unattached_transactions_content,
                {
                    'table': unattached_transactions_html,
                    'amortization_form': amortization_form_html
                }
            ),
            'amortize': render_to_string(
                self.amortizations_content_template,{'table': amortizations_table_html}
            )
        }

        template = 'api/views/amortizations.html'
        return render(request, template, context)

    def post(self, request):
        form = AmortizationForm(request.POST)
        if form.is_valid():
            form.save()
            unattached_transactions_html = self.get_unattached_prepaids_table_html()
            amortization_form_html = self.get_amortization_form_html()

            # amortize
            amortizations_table_html = self.get_amortization_table_html()

            context = {
                'unattached_transactions': render_to_string(
                    self.unattached_transactions_content,
                    {
                        'table': unattached_transactions_html,
                        'amortization_form': amortization_form_html
                    }
                ),
                'amortize': render_to_string(
                    self.amortizations_content_template,{'table': amortizations_table_html}
                )
            }

            template = 'api/views/amortizations.html'
            return render(request, template, context)

        print(form.errors)