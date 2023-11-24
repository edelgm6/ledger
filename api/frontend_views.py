from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View
from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.forms import modelformset_factory
from api.models import Transaction, Account, JournalEntry, JournalEntryItem
from api.forms import TransactionLinkForm, TransactionForm, TransactionFilterForm, JournalEntryItemForm, BaseJournalEntryItemFormset

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
class LinkTransactionsView(TransactionQueryMixin, JournalEntryFormMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    linked_transaction_form = TransactionLinkForm

    def get(self, request, *args, **kwargs):
        filter_form = TransactionFilterForm()
        transactions = self.get_filtered_queryset(request)

        # Default set form and transactions table to not closed
        filter_form['is_closed'].initial = False
        transactions = transactions.filter(is_closed=False)

        # Default set form and transactions table to not linked
        filter_form['has_linked_transaction'].initial = False
        transactions = transactions.filter(linked_transaction__isnull=True)

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
        transactions = self.get_filtered_queryset(request)

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
class TransactionsTableView(TransactionQueryMixin, JournalEntryFormMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, *args, **kwargs):
        transactions = self.get_filtered_queryset(request)
        transaction_id = transactions[0].id
        debit_formset, credit_formset = self.get_journal_entry_form(transaction_id=transaction_id)

        context = {
            'transactions': transactions,
            'transaction_id': transaction_id,
            'debit_formset': debit_formset,
            'credit_formset': credit_formset
        }

        # THIS WILL RETURN AN ERROR ON THE TRANSACTIONS LIST PAGE
        template = 'api/components/transactions-link-content.html'
        if self.kwargs.get('include_jei_form'):
            template = 'api/components/transactions-content.html'

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
class CreateJournalEntryItemsView(JournalEntryFormMixin, TransactionQueryMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    template = 'api/transactions-content.html'

    def _get_or_create_journal_entry(self, transaction):
        try:
            journal_entry = transaction.journal_entry
            # journal_entry.delete_journal_entry_items()
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

            transactions = self.get_filtered_queryset(request)
            transaction_id = transactions[0].id
            debit_formset, credit_formset = self.get_journal_entry_form(transaction_id=transaction_id)

            context = {
                'transactions': transactions,
                'transaction_id': transaction_id,
                'debit_formset': debit_formset,
                'credit_formset': credit_formset
            }

            return render(request, self.template, context)

class TransactionsListView(TransactionQueryMixin, JournalEntryFormMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    template = 'api/transactions-list.html'

    def get(self, request, *args, **kwargs):
        filter_form = TransactionFilterForm()
        transactions = self.get_filtered_queryset(request)

        # Default set form and transactions table to not closed
        filter_form['is_closed'].initial = False
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