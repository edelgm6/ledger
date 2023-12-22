from datetime import timedelta
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View
from django.shortcuts import get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.forms import modelformset_factory
from django.urls import reverse
from api.models import  Transaction, JournalEntry, JournalEntryItem
from api.forms import TransactionLinkForm, TransactionFilterForm, JournalEntryItemForm, BaseJournalEntryItemFormset, TransactionForm
from api import utils

class TransactionsViewMixin:
    filter_form_template = 'api/filter_forms/transactions-filter-form.html'

    def get_filter_form_html_and_objects(
        self,
        is_closed=None,
        has_linked_transaction=None,
        transaction_type=None,
        return_form_type=None,
        date_from=None,
        date_to=None
    ):
        form = TransactionFilterForm(prefix='filter')
        form.initial['is_closed'] = is_closed
        form.initial['has_linked_transaction'] = has_linked_transaction
        form.initial['transaction_type'] = transaction_type
        form.initial['date_from'] = utils.format_datetime_to_string(date_from) if date_from else None
        form.initial['date_to'] = utils.format_datetime_to_string(date_to) if date_to else None

        transactions = Transaction.objects.filter_for_table(
            is_closed=is_closed,
            has_linked_transaction=has_linked_transaction,
            transaction_types=transaction_type,
            date_from=date_from,
            date_to=date_to
        )

        context = {
            'filter_form': form,
            'return_form_type': return_form_type
        }

        return render_to_string(self.filter_form_template, context), transactions

    def get_table_html(self, transactions, index=0, no_highlight=False, row_url=None):

        context = {
            'transactions': transactions,
            'index': index,
            'no_highlight': no_highlight,
            'row_url': row_url
        }

        table_template = 'api/tables/transactions-table-new.html'
        return render_to_string(table_template, context)

class JournalEntryFormMixin:
    entry_form_template = 'api/entry_forms/journal-entry-item-form.html'

    def get_entry_form_html(self, transaction, index=0, debit_formset=None, credit_formset=None, is_debit=True, form_errors=None):
        if not transaction:
            return ''

        context = {}

        if not (debit_formset and credit_formset):
            try:
                journal_entry = transaction.journal_entry
                journal_entry_items = JournalEntryItem.objects.filter(journal_entry=journal_entry)
                journal_entry_debits = journal_entry_items.filter(type=JournalEntryItem.JournalEntryType.DEBIT)
                journal_entry_credits = journal_entry_items.filter(type=JournalEntryItem.JournalEntryType.CREDIT)
                bound_debits_count = journal_entry_debits.count()
                bound_credits_count = journal_entry_credits.count()
            except JournalEntry.DoesNotExist:
                bound_debits_count = 0
                bound_credits_count = 0
                journal_entry_debits = JournalEntryItem.objects.none()
                journal_entry_credits = JournalEntryItem.objects.none()

            debits_initial_data = []
            credits_initial_data = []

            if transaction.amount >= 0:
                is_debit = True
            else:
                is_debit = False

            prefill_debits_count = 0
            prefill_credits_count = 0
            if bound_debits_count + bound_credits_count == 0:
                primary_account, secondary_account = (transaction.account, transaction.suggested_account) \
                    if is_debit else (transaction.suggested_account, transaction.account)

                debits_initial_data.append({
                    'account': getattr(primary_account, 'name', None),
                    'amount': abs(transaction.amount)
                })

                credits_initial_data.append({
                    'account': getattr(secondary_account, 'name', None),
                    'amount': abs(transaction.amount)
                })

                if transaction.prefill:
                    prefill_items = transaction.prefill.prefillitem_set.all().order_by('order')
                    for item in prefill_items:
                        if item.journal_entry_item_type == JournalEntryItem.JournalEntryType.DEBIT:
                            debits_initial_data.append({'account': item.account.name, 'amount': 0})
                            prefill_debits_count += 1
                        else:
                            credits_initial_data.append({'account': item.account.name, 'amount': 0})
                            prefill_credits_count += 1

            debit_formset = modelformset_factory(JournalEntryItem, form=JournalEntryItemForm, formset=BaseJournalEntryItemFormset, extra=max((9-bound_debits_count),prefill_debits_count))
            credit_formset = modelformset_factory(JournalEntryItem, form=JournalEntryItemForm, formset=BaseJournalEntryItemFormset, extra=max((9-bound_credits_count),prefill_credits_count))

            debit_formset = debit_formset(queryset=journal_entry_debits, initial=debits_initial_data, prefix='debits')
            credit_formset = credit_formset(queryset=journal_entry_credits, initial=credits_initial_data, prefix='credits')

        prefilled_total = 0
        for form in debit_formset:
            try:
                prefilled_total += form.initial['amount']
            except KeyError:
                pass
        context = {
            'debit_formset': debit_formset,
            'credit_formset': credit_formset,
            'transaction_id': transaction.id,
            'index': index,
            'autofocus_debit': is_debit,
            'form_errors': form_errors,
            'prefilled_total': prefilled_total
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
                content_template  = 'api/content/transactions-link-content.html'
            else:
                table_html = self.get_table_html(transactions=transactions)
                try:
                    transaction=transactions[0]
                except IndexError:
                    transaction=None
                entry_form_html = self.get_entry_form_html(transaction=transaction)
                context['entry_form'] = entry_form_html
                content_template  = 'api/content/journal-entry-content.html'

            context['table'] = table_html

            html = render_to_string(content_template, context)
            return HttpResponse(html)

# ------------------Transactions View-----------------------

class TransactionFormView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, transaction_id):
        transaction = get_object_or_404(Transaction, pk=transaction_id)
        form = TransactionForm(instance=transaction)
        template = 'api/entry_forms/transaction-form.html'
        form_html = render_to_string(template, {'form': form, 'transaction': transaction})
        return HttpResponse(form_html)

class TransactionsView(TransactionsViewMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    content_template  = 'api/content/transactions-content.html'

    def get(self, request):
        last_two_months_last_days = utils.get_last_days_of_month_tuples()[0:2]
        last_day_of_last_month = last_two_months_last_days[0][0]
        first_day_of_last_month = last_two_months_last_days[1][0] + timedelta(days=1)

        filter_form_html, transactions = self.get_filter_form_html_and_objects(
            date_from=first_day_of_last_month,
            date_to=last_day_of_last_month
        )

        row_url = reverse('transactions')
        row_url += 'form/'
        table_html = self.get_table_html(
            transactions=transactions,
            no_highlight=True,
            row_url=row_url
        )

        transaction_form_html = render_to_string('api/entry_forms/transaction-form.html', {'form': TransactionForm()})
        context = {
            'filter_form': filter_form_html,
            'table_and_form': render_to_string(
                self.content_template,{
                    'table': table_html,
                    'transactions_form': transaction_form_html
                }
            )
        }

        view_template = 'api/views/transactions.html'
        html = render_to_string(view_template, context)
        return HttpResponse(html)

    def post(self, request, transaction_id=None):
        filter_form = TransactionFilterForm(request.POST, prefix='filter')
        if filter_form.is_valid():
            transactions = filter_form.get_transactions()
        else:
            print(filter_form.errors)

        if transaction_id:
            transaction = get_object_or_404(Transaction, pk=transaction_id)
            form = TransactionForm(request.POST, instance=transaction)
        else:
            form = TransactionForm(request.POST)

        if form.is_valid():
            transaction = form.save()
            form_template = 'api/entry_forms/transaction-form.html'
            form_html = render_to_string(
                form_template,
                {
                    'form': TransactionForm()
                 }
            )

            row_url = reverse('transactions')
            row_url += 'form/'
            table_html = self.get_table_html(
                transactions=transactions,
                no_highlight=True,
                row_url=row_url
            )

            content_template = 'api/content/transactions-content.html'
            context = {
                'transactions_form': form_html,
                'table': table_html
            }

            html = render_to_string(content_template, context)
            return HttpResponse(html)
        print(form.errors)

# ------------------Linking View-----------------------

class LinkTransactionsView(LinkFormMixin, TransactionsViewMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    content_template  = 'api/content/transactions-link-content.html'

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
    content_template  = 'api/content/journal-entry-content.html'

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
        transaction = get_object_or_404(Transaction,pk=transaction_id)

        # First check if the forms are valid and create JEIs if so
        has_errors = False
        form_errors = []
        if debit_formset.is_valid() and credit_formset.is_valid():
            debit_total = debit_formset.get_entry_total()
            credit_total = credit_formset.get_entry_total()
            if debit_total != credit_total:
                form_errors.append('Debits ($' + str(debit_total) + ') and Credits ($' + str(credit_total) + ') must balance.')
                has_errors = True

            account_amount = credit_formset.get_account_amount(transaction.account) if transaction.amount < 0 else debit_formset.get_account_amount(transaction.account)
            if account_amount != abs(transaction.amount):
                form_errors.append('At least one JEI must have the same account and amount as the transaction.')

        else:
            print(debit_formset.errors)
            has_errors = True

        if not has_errors:
            debit_formset.save(transaction, JournalEntryItem.JournalEntryType.DEBIT)
            credit_formset.save(transaction, JournalEntryItem.JournalEntryType.CREDIT)
            transaction.close()

        # Build the transactions table — use the filter settings if valid, else return all transactions
        filter_form = TransactionFilterForm(request.POST)
        if filter_form.is_valid():
            transactions = filter_form.get_transactions()
            index = int(request.POST.get('index', 0))  # Default to 0 if 'index' is not provided
        else:
            _, transactions = self.get_filter_form_html_and_objects(
                is_closed=False,
                transaction_type=[Transaction.TransactionType.INCOME,Transaction.TransactionType.PURCHASE]
            )
            index = 0

        # If either form has errors, return the forms to render the errors, else build it
        if has_errors:
            entry_form_html = self.get_entry_form_html(
                transaction=transaction,
                index=index,
                debit_formset=debit_formset,
                credit_formset=credit_formset,
                form_errors=form_errors
            )
        else:
            if len(transactions) == 0:
                entry_form_html = None
            else:
                # Need to check an index error in case user chose the last entry
                try:
                    highlighted_transaction = transactions[index]
                except IndexError:
                    index = 0
                    highlighted_transaction = transactions[index]
                entry_form_html = self.get_entry_form_html(transaction=highlighted_transaction, index=index)

        table_html = self.get_table_html(transactions=transactions, index=index)
        context = {
            'table': table_html,
            'entry_form': entry_form_html
        }
        html = render_to_string(self.content_template, context)
        return HttpResponse(html)