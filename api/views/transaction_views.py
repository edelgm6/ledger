from datetime import timedelta
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View
from django.shortcuts import get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.forms import modelformset_factory
from django.urls import reverse
from api.models import Transaction, JournalEntry, JournalEntryItem, Paystub, PaystubValue, S3File
from api.forms import (
    TransactionLinkForm, TransactionFilterForm, JournalEntryItemForm,
    BaseJournalEntryItemFormset, TransactionForm
)
from api import utils


class TransactionsViewMixin:
    filter_form_template = 'api/filter_forms/transactions-filter-form.html'
    entry_form_template = 'api/entry_forms/journal-entry-item-form.html'

    def get_paystubs_table_html(self):
        oustanding_textract_job_files = S3File.objects.filter(documents__isnull=True)
        for outstanding_textract_job_file in oustanding_textract_job_files:
            outstanding_textract_job_file.create_paystubs_from_textract_data()

        paystubs = Paystub.objects.filter(journal_entry__isnull=True).prefetch_related('paystub_values')
        paystubs_template = 'api/tables/paystubs-table.html'
        return render_to_string(paystubs_template, {'paystubs': paystubs})

    def get_filter_form_html_and_objects(
        self,
        is_closed=None,
        has_linked_transaction=None,
        transaction_type=None,
        date_from=None,
        date_to=None,
        get_url=None
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
        ).select_related('account')

        context = {
            'filter_form': form,
            'get_url': get_url
        }

        return (
            render_to_string(self.filter_form_template, context),
            transactions
        )

    def get_table_html(
            self, transactions, index=0, no_highlight=False, row_url=None
    ):

        context = {
            'transactions': transactions,
            'index': index,
            'no_highlight': no_highlight,
            'row_url': row_url
        }

        table_template = 'api/tables/transactions-table-new.html'
        return render_to_string(table_template, context)

    def get_transaction_form_html(
            self, transaction=None, created_transaction=None, change=None
    ):
        form_template = 'api/entry_forms/transaction-form.html'
        if transaction:
            form = TransactionForm(instance=transaction)
        else:
            form = TransactionForm()
        form_html = render_to_string(
            form_template,
            {
                'form': form,
                'transaction': transaction,
                'created_transaction': created_transaction,
                'change': change
            }
        )
        return form_html

    def get_journal_entry_form_html(
            self, transaction, index=0, debit_formset=None,
            credit_formset=None, is_debit=True, form_errors=None,
            paystub_id=None):
        if not transaction:
            return ''

        context = {}

        if not (debit_formset and credit_formset):
            try:
                journal_entry = transaction.journal_entry
                journal_entry_items = JournalEntryItem.objects.filter(
                    journal_entry=journal_entry
                )
                journal_entry_debits = journal_entry_items.filter(
                    type=JournalEntryItem.JournalEntryType.DEBIT
                )
                journal_entry_credits = journal_entry_items.filter(
                    type=JournalEntryItem.JournalEntryType.CREDIT
                )
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
                # TODO: Here's where I would insert the paystub prefills
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
                            debits_initial_data.append(
                                {'account': item.account.name, 'amount': 0}
                            )
                            prefill_debits_count += 1
                        else:
                            credits_initial_data.append({'account': item.account.name, 'amount': 0})
                            prefill_credits_count += 1

                if paystub_id:
                    paystub_values = PaystubValue.objects.filter(paystub__pk=paystub_id).select_related('account')
                    debits_initial_data = []
                    credits_initial_data = []
                    prefill_debits_count = 0
                    prefill_credits_count = 0
                    for paystub_value in paystub_values:
                        if paystub_value.journal_entry_item_type == JournalEntryItem.JournalEntryType.DEBIT:
                            debits_initial_data.append(
                                {'account': paystub_value.account.name, 'amount': paystub_value.amount}
                            )
                            prefill_debits_count += 1
                        else:
                            credits_initial_data.append({'account': item.account.name, 'amount': 0})
                            prefill_credits_count += 1


            debit_formset = modelformset_factory(JournalEntryItem, form=JournalEntryItemForm, formset=BaseJournalEntryItemFormset, extra=max((10-bound_debits_count), prefill_debits_count))
            credit_formset = modelformset_factory(JournalEntryItem, form=JournalEntryItemForm, formset=BaseJournalEntryItemFormset, extra=max((10-bound_credits_count), prefill_credits_count))

            debit_formset = debit_formset(queryset=journal_entry_debits, initial=debits_initial_data, prefix='debits')
            credit_formset = credit_formset(queryset=journal_entry_credits, initial=credits_initial_data, prefix='credits')

        # Set the total amounts for the debit and credits
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
            'prefilled_total': prefilled_total,
            'paystub_id': paystub_id
        }

        return render_to_string(self.entry_form_template, context)

    def get_link_form_html(self):
        entry_form_template = 'api/entry_forms/transaction-link-form.html'
        html = render_to_string(
            entry_form_template,
            {'link_form': TransactionLinkForm()}
        )
        return html

# ------------------Transactions View-----------------------


# Called by the filter form
class TransactionContentView(TransactionsViewMixin, LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        form = TransactionFilterForm(request.GET, prefix='filter')
        if form.is_valid():
            transactions = form.get_transactions()
            form_html = self.get_transaction_form_html()

            row_url = reverse('transactions')
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


# Called by table rows
class TransactionFormView(TransactionsViewMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, transaction_id=None):
        transaction = get_object_or_404(Transaction, pk=transaction_id)
        form_html = self.get_transaction_form_html(transaction=transaction)
        return HttpResponse(form_html)


# Called to load page or POST new objects
class TransactionsView(TransactionsViewMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    content_template = 'api/content/transactions-content.html'

    def get(self, request):
        last_two_months_last_days = utils.get_last_days_of_month_tuples()[0:2]
        last_day_of_last_month = last_two_months_last_days[0][0]
        first_day_of_last_month = (
            last_two_months_last_days[1][0] + timedelta(days=1)
        )

        filter_form_html, transactions = self.get_filter_form_html_and_objects(
            date_from=first_day_of_last_month,
            date_to=last_day_of_last_month,
            is_closed=False,
            get_url=reverse('transactions-content')
        )

        row_url = reverse('transactions')
        table_html = self.get_table_html(
            transactions=transactions,
            no_highlight=True,
            row_url=row_url
        )

        transaction_form_html = self.get_transaction_form_html()
        context = {
            'filter_form': filter_form_html,
            'table_and_form': render_to_string(
                self.content_template,
                {
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

        if request.POST['action'] == 'delete':
            form_html = self.get_transaction_form_html(created_transaction=transaction, change='delete')
            transaction.delete()
        elif request.POST['action'] == 'clear':
            form_html = self.get_transaction_form_html()
        elif form.is_valid():
            if transaction_id:
                change = 'update'
            else:
                change = 'create'
            transaction = form.save()
            form_html = self.get_transaction_form_html(created_transaction=transaction, change=change)

        row_url = reverse('transactions')
        table_html = self.get_table_html(
            transactions=transactions,
            no_highlight=True,
            row_url=row_url
        )

        content_template = 'api/content/transactions-content.html'
        context = {
            'transactions_form': form_html,
            'table': table_html,
            'transaction': transaction
        }

        html = render_to_string(content_template, context)
        return HttpResponse(html)

# ------------------Linking View-----------------------


# Called on filter
class LinkTransactionsContentView(
    TransactionsViewMixin, LoginRequiredMixin, View
):

    def get(self, request):
        form = TransactionFilterForm(request.GET, prefix='filter')
        if form.is_valid():
            transactions = form.get_transactions()

            table_html = self.get_table_html(transactions, no_highlight=True)
            link_form_html = self.get_link_form_html()
            context = {
                'table': table_html,
                'link_form': link_form_html
            }
            content_template = 'api/content/transactions-link-content.html'

            html = render_to_string(content_template, context)
            return HttpResponse(html)


# Called to load page and link transactions
class LinkTransactionsView(TransactionsViewMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    content_template = 'api/content/transactions-link-content.html'

    def get(self, request):
        filter_form_html, transactions = self.get_filter_form_html_and_objects(
            is_closed=False,
            has_linked_transaction=False,
            transaction_type=[
                Transaction.TransactionType.TRANSFER,
                Transaction.TransactionType.PAYMENT
            ],
            get_url=reverse('link-transactions-content')
        )
        table_html = self.get_table_html(transactions, no_highlight=True)
        link_form_html = self.get_link_form_html()

        context = {
            'filter_form': filter_form_html,
            'table_and_form': render_to_string(
                self.content_template,
                {
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
        filter_form = TransactionFilterForm(request.POST, prefix='filter')
        if filter_form.is_valid():
            transactions = filter_form.get_transactions()

            if form.is_valid():
                form.save()
                table_html = self.get_table_html(
                    transactions=transactions,
                    no_highlight=True
                )
                link_form_html = self.get_link_form_html()
                context = {
                    'table': table_html,
                    'link_form': link_form_html
                }

                html = render_to_string(self.content_template, context)
                return HttpResponse(html)

            print(form.errors)
            print(form.non_field_errors())