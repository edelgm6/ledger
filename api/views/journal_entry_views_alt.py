from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View

from api.models import Transaction
from api.services.journal_entry_services import (
    convert_frontend_list_to_python,
    get_journal_entry_form_html,
    get_transaction_store_to_html,
    remove_transaction_from_ids_list,
)

from api.views.mixins import JournalEntryViewMixin
from api.views.transaction_views import TransactionsViewMixin

"""
How this all works
1) Each row in the table can call the server to replace the form to a new transaction
2) A Data Store html component is passed to the front end with all of the transaction IDs
in the current table
3) When the form is processed, it references the Data Store object to figure out the next
transaction to preload
"""


class JournalEntryUpdate(View):
    # TODO: load the form plus button
    def post(self, request, transaction_id):
        print("journalentryupdate")
        # TODO: Process the post
        transaction = Transaction.objects.get(pk=transaction_id)

        transaction_ids = request.POST.get("transaction_ids")
        cleaned_transaction_ids, next_transaction = remove_transaction_from_ids_list(
            transaction_ids=transaction_ids, transaction_id=transaction_id
        )

        if not next_transaction:
            return HttpResponse("")
        html = get_journal_entry_form_html(transaction=next_transaction)
        transaction_store_html = get_transaction_store_to_html(
            transaction_ids=cleaned_transaction_ids, swap_oob=True
        )
        html += transaction_store_html
        response = HttpResponse(html)

        return response


class JournalEntryButton(View):
    def get(self, request, transaction_id):
        print("journalentrybutton")
        if not transaction_id:
            return ""

        transaction_ids = request.GET.get("transaction_ids")
        transaction_ids = convert_frontend_list_to_python(frontend_list=transaction_ids)

        transaction = Transaction.objects.get(pk=transaction_id)
        html = get_journal_entry_form_html(transaction=transaction)
        return HttpResponse(html)


# Called as the main page
class JournalEntryViewAlt(
    TransactionsViewMixin, JournalEntryViewMixin, LoginRequiredMixin, View
):
    login_url = "/login/"
    redirect_field_name = "next"
    view_template = "api/views/journal-entry-view-alt.html"

    def get_table_html(self, transactions):
        print("get_table_html")
        transaction_ids = transactions.values_list("id", flat=True)
        context = {"transactions": transactions, "transaction_ids": transaction_ids}

        table_template = "api/tables/transactions-table-alt.html"
        return render_to_string(table_template, context)

    def get(self, request):
        print("get")
        transactions = Transaction.objects.all().order_by("date")
        table_html = self.get_table_html(transactions=transactions)
        jei_form_html = get_journal_entry_form_html(transaction=transactions[0])
        transaction_ids = transactions.values_list("id", flat=True)
        transaction_store_html = get_transaction_store_to_html(
            transaction_ids=transaction_ids
        )
        context = {
            "table": table_html,
            "form": jei_form_html,
            "transaction_ids": transaction_ids,
            "transaction_store": transaction_store_html,
        }

        html = render_to_string(self.view_template, context)
        return HttpResponse(html)
