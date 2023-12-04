from datetime import date, datetime
import calendar
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.forms import modelformset_factory
from django.core.exceptions import ValidationError
from api.models import Reconciliation, TaxCharge, Transaction, Account, JournalEntry, JournalEntryItem
from api.forms import UploadTransactionsForm, ReconciliationFilterForm, ReconciliationForm, TaxChargeFilterForm, TaxChargeForm, TransactionLinkForm, TransactionForm, TransactionFilterForm, JournalEntryItemForm, BaseJournalEntryItemFormset
from api.statement import IncomeStatement, BalanceSheet

class UploadTransactionsView(View):

    form = UploadTransactionsForm
    template = 'api/views/upload-transactions.html'
    form_template = 'api/entry_forms/upload-form.html'

    def get(self, request):
        form_html = render_to_string(self.form_template, {'form': self.form})
        return render(request, self.template, {'form': form_html})

    def post(self, request):
        form = self.form(request.POST, request.FILES)
        if form.is_valid():
            transactions = form.save()
            form_html = render_to_string(self.form_template, {'form': form})
            success_html = render_to_string(
                'api/components/upload-success.html',
                {
                    'count': len(transactions),
                    'account': form.cleaned_data['account']
                }
            )
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
        reconciliations = reconciliations.order_by('account')
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

        template = 'api/reconciliation.html'
        reconciliations = Reconciliation.objects.filter(date=self._get_last_day_of_last_month())
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

class TransactionsViewMixin:
    filter_form_template = 'api/filter_forms/transactions-filter-form.html'
    table_template = 'api/tables/transactions-table.html'

    def get_filter_form_html_and_objects(
        self,
        is_closed=None,
        has_linked_transaction=None,
        transaction_type=None,
        return_form_type=None
    ):
        form = TransactionFilterForm()
        form.initial['is_closed'] = is_closed
        form.initial['has_linked_transaction'] = has_linked_transaction
        form.initial['transaction_type'] = transaction_type
        transactions = Transaction.objects.filter_for_table(is_closed, has_linked_transaction, transaction_type)

        context = {
            'filter_form': form,
            'return_form_type': return_form_type
        }

        return render_to_string(self.filter_form_template, context), transactions

    def get_table_html(self, transactions, index=0, no_highlight=False):

        context = {
            'transactions': transactions,
            'index': index,
            'no_highlight': no_highlight
        }

        return render_to_string(self.table_template, context)

class JournalEntryFormMixin:
    entry_form_template = 'api/entry_forms/journal-entry-item-form.html'

    def get_entry_form_html(self, transaction, index=0):
        if not transaction:
            return ''
        try:
            journal_entry = transaction.journal_entry
            journal_entry_items = JournalEntryItem.objects.filter(journal_entry=journal_entry)
            journal_entry_debits = journal_entry_items.filter(type=JournalEntryItem.JournalEntryType.DEBIT)
            journal_entry_credits = journal_entry_items.filter(type=JournalEntryItem.JournalEntryType.CREDIT)
            debits_count = journal_entry_debits.count()
            credits_count = journal_entry_credits.count()
        except JournalEntry.DoesNotExist:
            debits_count = 0
            credits_count = 0
            journal_entry_debits = JournalEntryItem.objects.none()
            journal_entry_credits = JournalEntryItem.objects.none()

        debit_formset = modelformset_factory(JournalEntryItem, form=JournalEntryItemForm, formset=BaseJournalEntryItemFormset, extra=9-debits_count)
        credit_formset = modelformset_factory(JournalEntryItem, form=JournalEntryItemForm, formset=BaseJournalEntryItemFormset, extra=9-credits_count)

        DEBITS_DECREASE_ACCOUNT_TYPES = [Account.Type.LIABILITY, Account.Type.EQUITY]
        debits_initial_data = []
        credits_initial_data = []

        is_debit = (transaction.amount < 0 and transaction.account.type in DEBITS_DECREASE_ACCOUNT_TYPES) or \
                (transaction.amount >= 0 and transaction.account.type not in DEBITS_DECREASE_ACCOUNT_TYPES)

        if debits_count + credits_count == 0:
            primary_account, secondary_account = (transaction.account, transaction.suggested_account) \
                if is_debit else (transaction.suggested_account, transaction.account)

            debits_initial_data.append({'account': primary_account, 'amount': abs(transaction.amount)})
            credits_initial_data.append({'account': secondary_account, 'amount': abs(transaction.amount)})

        debit_formset = debit_formset(queryset=journal_entry_debits, initial=debits_initial_data, prefix='debits')
        credit_formset = credit_formset(queryset=journal_entry_credits, initial=credits_initial_data, prefix='credits')
        context = {
            'debit_formset': debit_formset,
            'credit_formset': credit_formset,
            'transaction_id': transaction.id,
            'index': index,
            'autofocus_debit': is_debit
        }

        return render_to_string(self.entry_form_template, context)

class LinkFormMixin:
    def get_link_form_html(self):
        entry_form_template = 'api/entry_forms/transaction-link-form.html'
        html = render_to_string(
            entry_form_template,
            {'link_form': TransactionLinkForm()}
        )
        return html

# Called every time the page is filtered
class TransactionsTableView(LinkFormMixin, JournalEntryFormMixin, TransactionsViewMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, *args, **kwargs):
        form = TransactionFilterForm(request.GET)
        if form.is_valid():
            transactions = form.get_transactions()

            context = {}
            if request.GET.get('return_form_type') == 'link':
                table_html = self.get_table_html(transactions, no_highlight=True)
                link_form_html = self.get_link_form_html()
                context['link_form'] = link_form_html
                content_template  = 'api/components/transactions-link-content.html'
            else:
                table_html = self.get_table_html(transactions=transactions)
                try:
                    transaction=transactions[0]
                except IndexError:
                    transaction=None
                entry_form_html = self.get_entry_form_html(transaction=transaction)
                context['entry_form'] = entry_form_html
                content_template  = 'api/components/journal-entry-content.html'

            context['table'] = table_html

            html = render_to_string(content_template, context)
            return HttpResponse(html)

# ------------------Linking View-----------------------

class LinkTransactionsView(LinkFormMixin, TransactionsViewMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    content_template  = 'api/components/transactions-link-content.html'

    def get(self, request):
        filter_form_html, transactions = self.get_filter_form_html_and_objects(
            is_closed=False,
            has_linked_transaction=False,
            transaction_type=[Transaction.TransactionType.TRANSFER,Transaction.TransactionType.PAYMENT],
            return_form_type='link'
        )
        table_html = self.get_table_html(transactions, no_highlight=True)
        link_form_html = self.get_link_form_html()

        context = {
            'filter_form': filter_form_html,
            'table_and_form': render_to_string(
                self.content_template,{
                    'table': table_html,
                    'link_form': link_form_html
                }
            )
        }

        view_template = 'api/views/transactions-linking.html'
        html = render_to_string(view_template, context)
        return HttpResponse(html)

    def post(self, request):
        form = TransactionLinkForm(request.POST)
        filter_form = TransactionFilterForm(request.POST)
        if filter_form.is_valid():
            transactions = filter_form.get_transactions()

            if form.is_valid():
                form.save()
                table_html = self.get_table_html(transactions=transactions, no_highlight=True)
                link_form_html = self.get_link_form_html()
                context = {
                    'table': table_html,
                    'link_form': link_form_html
                }

                html = render_to_string(self.content_template, context)
                return HttpResponse(html)

            print(form.errors)
            print(form.non_field_errors())

# ------------------Journal Entries View-----------------------

# Called every time a table row is clicked
class JournalEntryFormView(JournalEntryFormMixin, TransactionsViewMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    item_form_template = 'api/entry_forms/journal-entry-item-form.html'

    def get(self, request, transaction_id):
        transaction = Transaction.objects.get(pk=transaction_id)
        entry_form_html = self.get_entry_form_html(transaction=transaction, index=request.GET.get('row_index'))

        return HttpResponse(entry_form_html)

# Called as the main page
class JournalEntryView(JournalEntryFormMixin, TransactionsViewMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    view_template = 'api/views/journal-entry-view.html'
    content_template  = 'api/components/journal-entry-content.html'

    def get(self, request):
        filter_form_html, transactions = self.get_filter_form_html_and_objects(
            is_closed=False,
            transaction_type=[Transaction.TransactionType.INCOME,Transaction.TransactionType.PURCHASE]
        )
        table_html = self.get_table_html(transactions)
        try:
            transaction=transactions[0]
        except IndexError:
            transaction = None
        entry_form_html = self.get_entry_form_html(transaction=transaction)

        context = {
            'filter_form': filter_form_html,
            'table_and_form': render_to_string(
                self.content_template,
                {'table': table_html,'entry_form': entry_form_html}
            )
        }

        html = render_to_string(self.view_template, context)
        return HttpResponse(html)

    def post(self, request, transaction_id):
        JournalEntryItemFormset = modelformset_factory(JournalEntryItem, formset=BaseJournalEntryItemFormset, form=JournalEntryItemForm)
        debit_formset = JournalEntryItemFormset(request.POST, prefix='debits')
        credit_formset = JournalEntryItemFormset(request.POST, prefix='credits')

        if debit_formset.is_valid() and credit_formset.is_valid():
            debit_total = debit_formset.get_entry_total()
            credit_total = credit_formset.get_entry_total()

            if debit_total != credit_total:
                return HttpResponse('debits and credits must match')

            transaction = Transaction.objects.get(pk=transaction_id)
            debit_formset.save(transaction, JournalEntryItem.JournalEntryType.DEBIT)
            credit_formset.save(transaction, JournalEntryItem.JournalEntryType.CREDIT)
            transaction.close()

            filter_form = TransactionFilterForm(request.POST)
            if filter_form.is_valid():
                transactions = filter_form.get_transactions()
                if request.POST.get('index'):
                    index = int(request.POST.get('index', 0))  # Default to 0 if 'index' is not provided
                    try:
                        transaction = transactions[index]
                        entry_form_html = self.get_entry_form_html(transaction=transaction, index=index)
                    except IndexError:
                        entry_form_html = None

                table_html = self.get_table_html(transactions=transactions, index=index)

                context = {
                    'table': table_html,
                    'entry_form': entry_form_html
                }

                html = render_to_string(self.content_template, context)
                return HttpResponse(html)
            print(filter_form.errors)

# ------------------Wallet Transactions View-----------------------

class IndexView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    template = 'api/views/index.html'
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