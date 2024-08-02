from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View
from django.shortcuts import get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.forms import modelformset_factory
from django.urls import reverse
from api.views.transaction_views import TransactionsViewMixin
from api.models import Transaction, JournalEntryItem, Paystub, PaystubValue, JournalEntry, S3File
from api.forms import (
    TransactionFilterForm, JournalEntryItemForm,
    BaseJournalEntryItemFormset, JournalEntryMetadataForm
)

class JournalEntryViewMixin:
    entry_form_template = 'api/entry_forms/journal-entry-item-form.html'

    def get_paystubs_table_html(self):
        oustanding_textract_job_files = S3File.objects.filter(documents__isnull=True)
        for outstanding_textract_job_file in oustanding_textract_job_files:
            outstanding_textract_job_file.create_paystubs_from_textract_data()

        paystubs = Paystub.objects.filter(journal_entry__isnull=True).prefetch_related('paystub_values').select_related('document')
        paystubs_template = 'api/tables/paystubs-table.html'
        return render_to_string(paystubs_template, {'paystubs': paystubs})

    def get_combined_formset_errors(
            self, debit_formset, credit_formset
        ):
        form_errors = []
        debit_total = debit_formset.get_entry_total()
        credit_total = credit_formset.get_entry_total()
        if debit_total != credit_total:
            form_errors.append('Debits ($' + str(debit_total) + ') and Credits ($' + str(credit_total) + ') must balance.')

        print(form_errors)
        return form_errors

    def check_for_errors(self, request, debit_formset, credit_formset, metadata_form, transaction):
        has_errors = False
        form_errors = []
        # Check if formsets have errors on their own, then check if they have errors
        # in the aggregate (e.g., don't have balanced credits/debits)
        if debit_formset.is_valid() and credit_formset.is_valid() and metadata_form.is_valid():
            form_errors = self.get_combined_formset_errors(
                debit_formset=debit_formset,
                credit_formset=credit_formset
            )
            has_errors = bool(form_errors)
        else:
            print(debit_formset.errors)
            print(credit_formset.errors)
            print(metadata_form.errors)
            has_errors = True

        if not has_errors:
            return False, None

        context = {
            'debit_formset': debit_formset,
            'credit_formset': credit_formset,
            'transaction_id': transaction.id,
            'autofocus_debit': True,
            'form_errors': form_errors,
            'prefilled_total': debit_formset.get_entry_total(),
            'debit_prefilled_total': debit_formset.get_entry_total(),
            'credit_prefilled_total': credit_formset.get_entry_total(),
            'metadata_form': metadata_form
        }

        html = render_to_string(self.entry_form_template, context)
        response = HttpResponse(html)
        response.headers['HX-Retarget'] = '#form-div'
        return True, response

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
                            credits_initial_data.append(
                                {'account': paystub_value.account.name, 'amount': paystub_value.amount}
                            )
                            prefill_credits_count += 1


            debit_formset = modelformset_factory(JournalEntryItem, form=JournalEntryItemForm, formset=BaseJournalEntryItemFormset, extra=max((10-bound_debits_count), prefill_debits_count))
            credit_formset = modelformset_factory(JournalEntryItem, form=JournalEntryItemForm, formset=BaseJournalEntryItemFormset, extra=max((10-bound_credits_count), prefill_credits_count))

            debit_formset = debit_formset(queryset=journal_entry_debits, initial=debits_initial_data, prefix='debits')
            credit_formset = credit_formset(queryset=journal_entry_credits, initial=credits_initial_data, prefix='credits')

        metadata = {
            'index': index,
            'paystub_id': paystub_id
        }
        metadata_form = JournalEntryMetadataForm(initial=metadata)
        # Set the total amounts for the debit and credits
        debit_prefilled_total = debit_formset.get_entry_total()
        credit_prefilled_total = credit_formset.get_entry_total()
        context = {
            'debit_formset': debit_formset,
            'credit_formset': credit_formset,
            'transaction_id': transaction.id,
            'autofocus_debit': is_debit,
            'form_errors': form_errors,
            'debit_prefilled_total': debit_prefilled_total,
            'credit_prefilled_total': credit_prefilled_total,
            'metadata_form': metadata_form
        }

        return render_to_string(self.entry_form_template, context)


# Called every time the page is filtered
class JournalEntryTableView(TransactionsViewMixin, JournalEntryViewMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, *args, **kwargs):
        form = TransactionFilterForm(request.GET, prefix='filter')
        if form.is_valid():
            transactions = form.get_transactions()
            table_html = self.get_table_html(
                transactions=transactions,
                row_url=reverse('journal-entries')
            )
            try:
                transaction = transactions[0]
            except IndexError:
                transaction = None
            entry_form_html = self.get_journal_entry_form_html(
                transaction=transaction
            )
            paystubs_table_html = self.get_paystubs_table_html()
            view_template = 'api/views/journal-entry-view.html'
            context = {
                'entry_form': entry_form_html,
                'table': table_html,
                'paystubs_table': paystubs_table_html,
                'transaction_id': transaction.id if transaction else None,
                'index': 0
            }

            html = render_to_string(view_template, context)
            return HttpResponse(html)


# Called every time a table row is clicked
# TODO: WTF shoudl I do here
class JournalEntryFormView(TransactionsViewMixin, JournalEntryViewMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    item_form_template = 'api/entry_forms/journal-entry-item-form.html'

    def get(self, request, transaction_id):
        transaction = Transaction.objects.get(pk=transaction_id)
        paystub_id = request.GET.get('paystub_id')
        entry_form_html = self.get_journal_entry_form_html(
            transaction=transaction,
            index=request.GET.get('row_index'),
            paystub_id=paystub_id
        )

        return HttpResponse(entry_form_html)

class PaystubDetailView(TransactionsViewMixin, LoginRequiredMixin, View):

    def get(self, request, paystub_id):
        paystub_values = PaystubValue.objects.filter(paystub__pk=paystub_id).select_related('account')
        template = 'api/tables/paystubs-table.html'
        html = render_to_string(
            template, 
            {
                'paystub_values': paystub_values,
                'paystub_id': paystub_id
            }
        )
        return HttpResponse(html)

# Called as the main page
class JournalEntryView(TransactionsViewMixin, JournalEntryViewMixin, LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'
    view_template = 'api/views/journal-entry-view.html'

    def get(self, request):
        # Collect HTML for all components in view
        filter_form_html, transactions = self.get_filter_form_html_and_objects(
            is_closed=False,
            transaction_type=[
                Transaction.TransactionType.INCOME,
                Transaction.TransactionType.PURCHASE
            ],
            get_url=reverse('journal-entries-table')
        )
        table_html = self.get_table_html(
            transactions=transactions,
            row_url=reverse('journal-entries')
        )
        try:
            transaction = transactions[0]
        except IndexError:
            transaction = None
        entry_form_html = self.get_journal_entry_form_html(
            transaction=transaction
        )
        paystubs_table_html = self.get_paystubs_table_html()
        context = {
            'filter_form': filter_form_html,
            'table': table_html, 
            'entry_form': entry_form_html,
            'paystubs_table': paystubs_table_html,
            'index': 0,
            'transaction_id': transactions[index].pk if transactions else None,
            'is_initial_load': True
        }

        html = render_to_string(self.view_template, context)
        return HttpResponse(html)

    def post(self, request, transaction_id):
        # Build formsets for the credit and debit side of the JE and get transaction
        # and metadata form
        JournalEntryItemFormset = modelformset_factory(
            JournalEntryItem,
            formset=BaseJournalEntryItemFormset,
            form=JournalEntryItemForm
        )
        debit_formset = JournalEntryItemFormset(request.POST, prefix='debits')
        credit_formset = JournalEntryItemFormset(
            request.POST,
            prefix='credits'
        )
        metadata_form = JournalEntryMetadataForm(request.POST)
        transaction = get_object_or_404(Transaction, pk=transaction_id)

        # First check if the forms are valid and return errors if not
        has_errors, response = self.check_for_errors(
            debit_formset=debit_formset,
            credit_formset=credit_formset,
            request=request,
            transaction=transaction,
            metadata_form=metadata_form
        )
        if has_errors:
            return response

        debit_formset.save(
            transaction,
            JournalEntryItem.JournalEntryType.DEBIT
        )
        credit_formset.save(
            transaction,
            JournalEntryItem.JournalEntryType.CREDIT
        )
        transaction.close()
        
        # If there's an attached paystub in the GET request, close it out
        paystub_id = metadata_form.cleaned_data.get('paystub_id')
        try:
            paystub = Paystub.objects.get(pk=paystub_id)
            paystub.journal_entry = transaction.journal_entry
            paystub.save()
        except ValueError:
            pass

        # Build the transactions table — use the existing filter settings if valid,
        # else return all transactions
        filter_form = TransactionFilterForm(request.POST, prefix='filter')
        if filter_form.is_valid():
            transactions = filter_form.get_transactions()
            index = metadata_form.cleaned_data['index']
        else:
            _, transactions = self.get_filter_form_html_and_objects(
                is_closed=False,
                transaction_type=[
                    Transaction.TransactionType.INCOME,
                    Transaction.TransactionType.PURCHASE
                ]
            )
            index = 0

        if len(transactions) == 0:
            entry_form_html = ''
        else:
            # Need to check an index error in case
            # user chose the last entry
            try:
                highlighted_transaction = transactions[index]
            except IndexError:
                index = 0
                highlighted_transaction = transactions[index]
            entry_form_html = self.get_journal_entry_form_html(
                transaction=highlighted_transaction,
                index=index
            )

        table_html = self.get_table_html(
            transactions=transactions,
            index=index,
            row_url=reverse('journal-entries')
        )
        paystubs_table_html = self.get_paystubs_table_html()
        context = {
            'table': table_html,
            'entry_form': entry_form_html,
            'index': index,
            'transaction_id': transactions[index].pk if transactions else None,
            'paystubs_table': paystubs_table_html
        }
        html = render_to_string(self.view_template, context)
        return HttpResponse(html)