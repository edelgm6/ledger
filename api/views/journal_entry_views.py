from django.contrib.auth.mixins import LoginRequiredMixin
from django.forms import modelformset_factory
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.views import View

from api.forms import (
    BaseJournalEntryItemFormset,
    JournalEntryItemForm,
    JournalEntryMetadataForm,
    TransactionFilterForm,
)
from api.models import JournalEntryItem, Paystub, PaystubValue, Transaction
from api.services.journal_entry_services import get_accounts_choices
from api.views.mixins import JournalEntryViewMixin
from api.views.transaction_views import TransactionsViewMixin


class TriggerAutoTagView(LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request):
        open_transactions = Transaction.objects.filter(is_closed=False)
        Transaction.apply_autotags(open_transactions)

        open_transactions.bulk_update(
            open_transactions,
            ["suggested_account", "prefill", "type", "suggested_entity"],
        )

        return HttpResponse("<small class=text-success>Autotag complete</small>")


# Called every time the page is filtered
class JournalEntryTableView(
    TransactionsViewMixin, JournalEntryViewMixin, LoginRequiredMixin, View
):
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, *args, **kwargs):
        form = TransactionFilterForm(request.GET, prefix="filter")
        if form.is_valid():
            transactions = form.get_transactions()
            table_html = self.get_table_html(
                transactions=transactions, row_url=reverse("journal-entries")
            )
            try:
                transaction = transactions[0]
            except IndexError:
                transaction = None
            entry_form_html = self.get_journal_entry_form_html(transaction=transaction)
            paystubs_table_html = self.get_paystubs_table_html()
            view_template = "api/views/journal-entry-view.html"
            context = {
                "entry_form": entry_form_html,
                "table": table_html,
                "paystubs_table": paystubs_table_html,
                "transaction_id": transaction.id if transaction else None,
                "index": 0,
            }

            html = render_to_string(view_template, context)
            return HttpResponse(html)


# Called every time a table row is clicked
class JournalEntryFormView(
    TransactionsViewMixin, JournalEntryViewMixin, LoginRequiredMixin, View
):
    login_url = "/login/"
    redirect_field_name = "next"
    item_form_template = "api/entry_forms/journal-entry-item-form.html"

    def get(self, request, transaction_id):
        transaction = Transaction.objects.select_related("journal_entry").get(
            pk=transaction_id
        )
        paystub_id = request.GET.get("paystub_id")
        entry_form_html = self.get_journal_entry_form_html(
            transaction=transaction,
            index=request.GET.get("row_index"),
            paystub_id=paystub_id,
        )

        return HttpResponse(entry_form_html)


class PaystubTableView(JournalEntryViewMixin, LoginRequiredMixin, View):
    def get(self, request):
        html = self.get_paystubs_table_html()
        return HttpResponse(html)


class PaystubDetailView(TransactionsViewMixin, LoginRequiredMixin, View):

    def get(self, request, paystub_id):
        paystub_values = PaystubValue.objects.filter(
            paystub__pk=paystub_id
        ).select_related("account")
        template = "api/tables/paystubs-table.html"
        html = render_to_string(
            template, {"paystub_values": paystub_values, "paystub_id": paystub_id}
        )
        return HttpResponse(html)


# Called as the main page
class JournalEntryView(
    TransactionsViewMixin, JournalEntryViewMixin, LoginRequiredMixin, View
):
    login_url = "/login/"
    redirect_field_name = "next"
    view_template = "api/views/journal-entry-view.html"

    def get(self, request):
        # Collect HTML for all components in view
        filter_form_html, transactions = self.get_filter_form_html_and_objects(
            is_closed=False,
            transaction_type=[
                Transaction.TransactionType.INCOME,
                Transaction.TransactionType.PURCHASE,
            ],
            get_url=reverse("journal-entries-table"),
        )
        table_html = self.get_table_html(
            transactions=transactions, row_url=reverse("journal-entries")
        )
        try:
            transaction = transactions[0]
        except IndexError:
            transaction = None
        entry_form_html = self.get_journal_entry_form_html(transaction=transaction)
        paystubs_table_html = self.get_paystubs_table_html()
        context = {
            "filter_form": filter_form_html,
            "table": table_html,
            "entry_form": entry_form_html,
            "paystubs_table": paystubs_table_html,
            "index": 0,
            "transaction_id": transactions[0].pk if transactions else None,
            "is_initial_load": True,
        }

        html = render_to_string(self.view_template, context)
        return HttpResponse(html)

    def post(self, request, transaction_id):
        # Build formsets for the credit and debit side of the JE and get transaction
        # and metadata form
        JournalEntryItemFormset = modelformset_factory(
            JournalEntryItem,
            formset=BaseJournalEntryItemFormset,
            form=JournalEntryItemForm,
        )

        accounts_choices = get_accounts_choices()
        debit_formset = JournalEntryItemFormset(
            request.POST,
            prefix="debits",
            form_kwargs={"open_accounts_choices": accounts_choices},
        )
        credit_formset = JournalEntryItemFormset(
            request.POST,
            prefix="credits",
            form_kwargs={"open_accounts_choices": accounts_choices},
        )
        metadata_form = JournalEntryMetadataForm(request.POST)
        transaction = get_object_or_404(Transaction, pk=transaction_id)

        # First check if the forms are valid and return errors if not
        has_errors, response = self.check_for_errors(
            debit_formset=debit_formset,
            credit_formset=credit_formset,
            request=request,
            transaction=transaction,
            metadata_form=metadata_form,
        )
        if has_errors:
            return response

        debit_formset.save(transaction, JournalEntryItem.JournalEntryType.DEBIT)
        credit_formset.save(transaction, JournalEntryItem.JournalEntryType.CREDIT)
        transaction.close()

        # If there's an attached paystub in the GET request, close it out
        paystub_id = metadata_form.cleaned_data.get("paystub_id")
        try:
            paystub = Paystub.objects.get(pk=paystub_id)
            paystub.journal_entry = transaction.journal_entry
            paystub.save()
        except ValueError:
            pass

        # Build the transactions table — use the existing filter settings if valid,
        # else return all transactions
        filter_form = TransactionFilterForm(request.POST, prefix="filter")
        if filter_form.is_valid():
            transactions = filter_form.get_transactions()
            index = metadata_form.cleaned_data["index"]
        else:
            _, transactions = self.get_filter_form_html_and_objects(
                is_closed=False,
                transaction_type=[
                    Transaction.TransactionType.INCOME,
                    Transaction.TransactionType.PURCHASE,
                ],
            )
            index = 0

        if len(transactions) == 0:
            entry_form_html = ""
        else:
            # Need to check an index error in case
            # user chose the last entry
            try:
                highlighted_transaction = transactions[index]
            except IndexError:
                index = 0
                highlighted_transaction = transactions[index]

            created_entities = self.get_created_entities(
                formsets=[debit_formset, credit_formset]
            )
            entry_form_html = self.get_journal_entry_form_html(
                transaction=highlighted_transaction,
                index=index,
                created_entities=created_entities,
            )

        table_html = self.get_table_html(
            transactions=transactions, index=index, row_url=reverse("journal-entries")
        )
        paystubs_table_html = self.get_paystubs_table_html()
        context = {
            "table": table_html,
            "entry_form": entry_form_html,
            "index": index,
            "transaction_id": transactions[index].pk if transactions else None,
            "paystubs_table": paystubs_table_html,
        }
        html = render_to_string(self.view_template, context)
        return HttpResponse(html)
