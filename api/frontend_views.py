from datetime import date, datetime
import calendar
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.forms import modelformset_factory
from api.models import Reconciliation, TaxCharge, Transaction, Account, JournalEntry, JournalEntryItem
from api.forms import UploadTransactionsForm, ReconciliationFilterForm, ReconciliationForm, TaxChargeFilterForm, TaxChargeForm, TransactionLinkForm, TransactionForm, TransactionFilterForm, JournalEntryItemForm, BaseJournalEntryItemFormset
from api.statement import IncomeStatement, BalanceSheet

class FilterFormMixIn:
    def get_filter_form_html(self, request=None, form_include=None, is_closed=None, has_linked_transaction=None, transaction_type=None):
        form = TransactionFilterForm()
        form.initial['is_closed'] = is_closed
        form.initial['has_linked_transaction'] = has_linked_transaction
        form.initial['transaction_type'] = transaction_type
        if request:
            data = request.GET if request.GET else request.POST
            form = TransactionFilterForm(data)

        template = 'api/components/transactions-filter-form.html'

        context = {
            'filter_form': form,
            'form_include': form_include
        }

        return render_to_string(template, context)

class TransactionQueryMixin:
    def get_filtered_queryset(self, request):
        queryset = Transaction.objects.all()
        data = request.GET if request.GET else request.POST
        form = TransactionFilterForm(data)

        if form.is_valid():
            if form.cleaned_data.get('date_from'):
                queryset = queryset.filter(date__gte=form.cleaned_data['date_from'])
            if form.cleaned_data.get('date_to'):
                queryset = queryset.filter(date__lte=form.cleaned_data['date_to'])
            if form.cleaned_data.get('is_closed') is not None:
                queryset = queryset.filter(is_closed=form.cleaned_data['is_closed'])
            if form.cleaned_data['account']:
                queryset = queryset.filter(account__in=form.cleaned_data['account'])
            if form.cleaned_data['transaction_type']:
                queryset = queryset.filter(type__in=form.cleaned_data['transaction_type'])
            if form.cleaned_data.get('has_linked_transaction') is not None:
                queryset = queryset.exclude(linked_transaction__isnull=form.cleaned_data['has_linked_transaction'])

        return queryset.order_by('date','account')

class JournalEntryFormMixin:
    def get_journal_entry_form(self, transaction_id):
        transaction = Transaction.objects.get(pk=transaction_id)
        try:
            journal_entry = transaction.journal_entry
            journal_entry_items = JournalEntryItem.objects.filter(journal_entry=journal_entry)
            journal_entry_debits = journal_entry_items.filter(type=JournalEntryItem.JournalEntryType.DEBIT)
            journal_entry_credits = journal_entry_items.filter(type=JournalEntryItem.JournalEntryType.CREDIT)
            debits_count = journal_entry_debits.count()
            credits_count = journal_entry_credits.count()
        except (JournalEntry.DoesNotExist):
            debits_count = 0
            credits_count = 0
            journal_entry_debits = JournalEntryItem.objects.none()
            journal_entry_credits = JournalEntryItem.objects.none()

        debit_formset = modelformset_factory(JournalEntryItem, form=JournalEntryItemForm, formset=BaseJournalEntryItemFormset, extra=8-debits_count)
        credit_formset = modelformset_factory(JournalEntryItem, form=JournalEntryItemForm, formset=BaseJournalEntryItemFormset, extra=8-credits_count)

        DEBITS_DECREASE_ACCOUNT_TYPES = [Account.Type.LIABILITY, Account.Type.EQUITY]
        debits_initial_data = []
        credits_initial_data = []
        if debits_count + credits_count == 0:
            is_debit = (transaction.amount < 0 and transaction.account.type in DEBITS_DECREASE_ACCOUNT_TYPES) or \
                    (transaction.amount >= 0 and transaction.account.type not in DEBITS_DECREASE_ACCOUNT_TYPES)

            primary_account, secondary_account = (transaction.account, transaction.suggested_account) \
                if is_debit else (transaction.suggested_account, transaction.account)

            debits_initial_data.append({'account': primary_account, 'amount': abs(transaction.amount)})
            credits_initial_data.append({'account': secondary_account, 'amount': abs(transaction.amount)})

        return debit_formset(queryset=journal_entry_debits, initial=debits_initial_data, prefix='debits'), credit_formset(queryset=journal_entry_credits, initial=credits_initial_data, prefix='credits')

class UploadTransactionsView(View):

    form = UploadTransactionsForm
    template = 'api/upload-transactions.html'
    form_template = 'api/components/upload-form.html'

    def get(self, request):
        form_html = render_to_string(self.form_template, {'form': self.form})
        return render(request, self.template, {'form': form_html})

    def post(self, request):
        form = self.form(request.POST, request.FILES)
        if form.is_valid():
            transactions = form.save()
            form_html = render_to_string(self.form_template, {'form': form})
            success_html = render_to_string('api/components/upload-success.html', {'count': len(transactions)})
            return render(request, self.template, {'form': form_html, 'success': success_html})

class TaxTableMixIn:

    def get_tax_table_html(self, tax_charges):

        tax_charges = tax_charges.order_by('date','type')
        for tax_charge in tax_charges:
            last_day_of_month = tax_charge.date
            first_day_of_month = date(last_day_of_month.year, last_day_of_month.month, 1)
            taxable_income = IncomeStatement(tax_charge.date, first_day_of_month).get_taxable_income()
            tax_charge.taxable_income = taxable_income
            tax_charge.tax_rate = None if taxable_income == 0 else tax_charge.amount / taxable_income

        tax_charge_table_html = render_to_string(
            'api/components/tax-table.html',
            {'tax_charges': tax_charges}
        )

        return tax_charge_table_html

class ReconciliationTableMixin:

    def _get_current_balance(self, reconciliation):
        balance_sheet = BalanceSheet(reconciliation.date)
        balance = balance_sheet.get_balance(reconciliation.account)
        return balance

    def get_reconciliation_html(self, reconciliations):
        for reconciliation in reconciliations:
            reconciliation.current_balance = self._get_current_balance(reconciliation)

        ReconciliationFormset = modelformset_factory(Reconciliation, ReconciliationForm, extra=0)
        formset = ReconciliationFormset(queryset=reconciliations)
        zipped_reconciliations = zip(reconciliations, formset)

        template = 'api/components/reconciliation-table.html'
        return render_to_string(
            template,
            {
                'zipped_reconciliations': zipped_reconciliations,
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
            if request.GET.get('generate'):
                reconciliations = form.generate_reconciliations()
            else:
                reconciliations = form.get_reconciliations()

            reconciliations_table = self.get_reconciliation_html(reconciliations)
            return HttpResponse(reconciliations_table)

# Loads full page
class ReconciliationView(ReconciliationTableMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def _get_last_day_of_current_month(self):
        current_date = datetime.now()
        year = current_date.year
        month = current_date.month

        _, last_day = calendar.monthrange(year, month)
        last_day_date = date(year, month, last_day)

        return last_day_date

    def get(self, request, *args, **kwargs):

        template = 'api/reconciliation.html'
        reconciliations = Reconciliation.objects.filter(date=self._get_last_day_of_current_month())
        reconciliation_table = self.get_reconciliation_html(reconciliations)
        context = {
            'reconciliation_table': reconciliation_table,
            'filter_form': render_to_string(
                'api/components/reconciliation-filter-form.html',
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

        filter_form = ReconciliationFilterForm(request.POST)
        if filter_form.is_valid():
            reconciliations = filter_form.get_reconciliations()

        reconciliation_table = self.get_reconciliation_html(reconciliations)

        return HttpResponse(reconciliation_table)


class TaxChargeTableView(TaxTableMixIn, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, *args, **kwargs):
        form = TaxChargeFilterForm(request.GET)
        if form.is_valid():
            tax_charges = form.get_tax_charges()
            tax_table_charge_table_html = self.get_tax_table_html(tax_charges)

            template = 'api/components/taxes-content.html'
            form_template = 'api/components/edit-tax-charge-form.html'
            context = {
                'tax_charge_table': tax_table_charge_table_html,
                'form': render_to_string(form_template, {'form': TaxChargeForm()}),
            }

            return render(request, template, context)

# Add in the Taxes table mixin
class TaxChargeFormView(TaxTableMixIn, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    form_class = TaxChargeForm
    form_template = 'api/components/edit-tax-charge-form.html'

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
    form_template = 'api/components/edit-tax-charge-form.html'

    def get(self, request, *args, **kwargs):

        tax_charge_table = self.get_tax_table_html(TaxCharge.objects.all())
        template = 'api/taxes.html'
        filter_template = 'api/components/tax-charge-filter-form.html'
        context = {
            'tax_charge_table': tax_charge_table,
            'form': render_to_string(self.form_template, {'form': TaxChargeForm()}),
            'filter_form': render_to_string(filter_template, {'filter_form': TaxChargeFilterForm()})
        }

        return render(request, template, context)

# Loads full page
class LinkTransactionsView(FilterFormMixIn, JournalEntryFormMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    linked_transaction_form = TransactionLinkForm

    def get(self, request, *args, **kwargs):
        filter_form = self.get_filter_form_html(is_closed=False, has_linked_transaction=False, form_include='link-form', transaction_type=Transaction.TransactionType.TRANSFER)
        transactions = Transaction.objects.all().order_by('date','account')

        # Default set form and transactions table to not closed
        transactions = transactions.filter(is_closed=False)
        # Default set form and transactions table to not linked
        transactions = transactions.filter(linked_transaction__isnull=True)
        transactions = transactions.filter(type=Transaction.TransactionType.TRANSFER)

        template = 'api/transactions-linking.html'
        context = {
            'filter_form': filter_form,
            'transactions': transactions,
            'linked_transaction_form': self.linked_transaction_form,
            'no_highlight': True
        }
        return render(request, template, context)

    def post(self, request, *args, **kwargs):
        form = self.linked_transaction_form(request.POST)
        filter_form = TransactionFilterForm(request.POST)
        if filter_form.is_valid():
            transactions = filter_form.get_transactions()

        if form.is_valid():
            form.save()

            template = 'api/components/transactions-link-content.html'
            context = {
                'transactions': transactions,
                'linked_transaction_form': form,
                'no_highlight': True
            }
            return render(request, template, context)
        print(form.errors)

# Called by transactions filter form
class TransactionsTableView(JournalEntryFormMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, *args, **kwargs):
        data = request.GET if request.GET else request.POST
        form = TransactionFilterForm(data)
        if form.is_valid():
            transactions = form.get_transactions()

            transaction_id = transactions[0].id
            debit_formset, credit_formset = self.get_journal_entry_form(transaction_id=transaction_id)

            context = {
                'transactions': transactions,
                'transaction_id': transaction_id,
                'debit_formset': debit_formset,
                'credit_formset': credit_formset
            }

            if request.GET.get('returnForm'):
                if request.GET.get('returnForm') == 'jei-form':
                    template = 'api/components/transactions-content.html'
                elif request.GET.get('returnForm') == 'link-form':
                    template = 'api/components/transactions-link-content.html'

            return render(request, template, context)

# Called every time a table row is clicked
class JournalEntryFormView(JournalEntryFormMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    item_form_template = 'api/components/journal-entry-item-form.html'

    def get(self, request, *args, **kwargs):
        transaction_id = self.kwargs.get('transaction_id')
        debit_formset, credit_formset = self.get_journal_entry_form(transaction_id)

        context = {
            'transaction_id': transaction_id,
            'debit_formset': debit_formset,
            'credit_formset': credit_formset
        }
        return render(request, self.item_form_template, context)

# Called every time Submit is clicked. Should update table + form
# Fold this into the view that loads the page
class CreateJournalEntryItemsView(JournalEntryFormMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    template = 'api/components/transactions-content.html'

    def _get_or_create_journal_entry(self, transaction):
        try:
            journal_entry = transaction.journal_entry
        except JournalEntry.DoesNotExist:
            journal_entry = JournalEntry.objects.create(
                date=transaction.date,
                transaction=transaction
            )

        return journal_entry

    def post(self, request, *args, **kwargs):
        JournalEntryItemFormset = modelformset_factory(JournalEntryItem, formset=BaseJournalEntryItemFormset, form=JournalEntryItemForm)
        debit_formset = JournalEntryItemFormset(request.POST, request.FILES, prefix='debits')
        credit_formset = JournalEntryItemFormset(request.POST, request.FILES, prefix='credits')

        if debit_formset.is_valid() and credit_formset.is_valid():
            transaction_id = self.kwargs.get('transaction_id')
            transaction = Transaction.objects.get(pk=transaction_id)
            journal_entry = self._get_or_create_journal_entry(transaction)

            debit_total = debit_formset.get_entry_total()
            credit_total = credit_formset.get_entry_total()

            if debit_total != credit_total:
                raise ValidationError('debits and credits must match')

            debit_formset.save(journal_entry, JournalEntryItem.JournalEntryType.DEBIT)
            credit_formset.save(journal_entry, JournalEntryItem.JournalEntryType.CREDIT)

            transaction.close()

            filter_form = TransactionFilterForm(request.POST)
            if filter_form.is_valid():
                transactions = filter_form.get_transactions()
            transaction_id = transactions[0].id
            debit_formset, credit_formset = self.get_journal_entry_form(transaction_id=transaction_id)

            context = {
                'transactions': transactions,
                'transaction_id': transaction_id,
                'debit_formset': debit_formset,
                'credit_formset': credit_formset
            }

            return render(request, self.template, context)

class TransactionsListView(FilterFormMixIn, JournalEntryFormMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    template = 'api/transactions-list.html'

    def get(self, request, *args, **kwargs):
        filter_form = self.get_filter_form_html(form_include='jei-form', is_closed=False)
        transactions = Transaction.objects.all().order_by('date','account')
        transactions = transactions.filter(is_closed=False)

        transaction_id = transactions[0].id
        debit_formset, credit_formset = self.get_journal_entry_form(transaction_id=transaction_id)

        context = {
            'filter_form': filter_form,
            'transactions': transactions,
            'transaction_id': transaction_id,
            'debit_formset': debit_formset,
            'credit_formset': credit_formset
        }
        return render(request, self.template, context)

class IndexView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    template = 'api/index.html'
    success_template = 'api/wallet-success.html'
    form_class = TransactionForm

    def get(self, request, *args, **kwargs):
        return render(request, self.template, {'form': self.form_class,'today': timezone.localdate()})

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)
        if form.is_valid():
            transaction = form.save()
            success = render_to_string(self.success_template, {'transaction': transaction})
            return HttpResponse(success)

        return render(request, self.template_name, {'form': form})