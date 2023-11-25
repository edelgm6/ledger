from datetime import date
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.forms import modelformset_factory
from api.models import TaxCharge, Transaction, Account, JournalEntry, JournalEntryItem
from api.forms import TaxChargeForm, TransactionLinkForm, TransactionForm, TransactionFilterForm, JournalEntryItemForm, BaseJournalEntryItemFormset
from api.statement import IncomeStatement

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

# Loads full page
class EditTaxChargeView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, pk=None, *args, **kwargs):

        template = 'api/components/edit-tax-charge-form.html'
        if pk:
            tax_charge = get_object_or_404(TaxCharge, pk=pk)
            form = TaxChargeForm(instance=tax_charge)
        else:
            form = TaxChargeForm()

        context = {'form': form}
        return render(request, template, context)

# Loads full page
class TaxesView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, *args, **kwargs):

        template = 'api/taxes.html'

        tax_charges = TaxCharge.objects.all()

        for tax_charge in tax_charges:
            last_day_of_month = tax_charge.date
            first_day_of_month = date(last_day_of_month.year, last_day_of_month.month, 1)
            taxable_income = IncomeStatement(tax_charge.date, first_day_of_month).get_taxable_income()
            tax_charge.taxable_income = taxable_income
            tax_charge.tax_rate = None if taxable_income == 0 else tax_charge.amount / taxable_income

        tax_charge_table = render_to_string(
            'api/components/tax-table.html',
            {'tax_charges': tax_charges}
        )
        context = {'tax_charge_table': tax_charge_table}
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
                # transactions = self.get_filtered_queryset(request)
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