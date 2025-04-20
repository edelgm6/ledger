import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.views import View

from api.models import Transaction
from api.services.journal_entry_services import (
    convert_frontend_list_to_python,
    get_journal_entry_form_html,
)
from api.views.mixins import JournalEntryViewMixin
from api.views.transaction_views import TransactionsViewMixin

"""
How this all works
1) Each row in the table is aware of itself, plus the id of the next row and the next next row
2) When a row is clicked, it creates a form that is aware of the selected row, the next row, and the next next row
3) When the form is processed, it passes back the new form, which is aware of the current transaction (previously the next row) 
plus the next transaction (previously the next next row)
"""


class JournalEntryUpdate(View):
    
    # TODO: load the form plus button
    def post(self, request, transaction_id):
        print('journalentryupdate')
        # TODO: Process the post

        transaction_ids = request.POST.get('transaction_ids')
        transaction_ids = convert_frontend_list_to_python(frontend_list=transaction_ids)
        transaction = Transaction.objects.get(pk=transaction_id)
        transaction_index = transaction_ids.index(transaction_id)

        print(transaction_ids)
        print(transaction_id)
        print(transaction_index)
        print(len(transaction_ids))
        if transaction_index < len(transaction_ids) - 1:
            next_transaction = Transaction.objects.get(pk=transaction_ids[transaction_index + 1])
            transaction_ids.remove(transaction_id)
            print(transaction_ids)
            html = get_journal_entry_form_html(transaction=next_transaction, transaction_ids=transaction_ids)
        else:
            html = ''

        response = HttpResponse(html)

        return response

class JournalEntryButton(View):
    
    def get(self, request, transaction_id):
        print('journalentrybutton')
        if not transaction_id:
            return ""
        
        transaction_ids = request.GET.get('transaction_ids')
        transaction_ids = convert_frontend_list_to_python(frontend_list=transaction_ids)
        # transaction_ids = transaction_ids.split(',')
        # print(transaction_ids)

        transaction = Transaction.objects.get(pk=transaction_id)
        html = get_journal_entry_form_html(transaction=transaction, transaction_ids=transaction_ids)
        return HttpResponse(html)

# Called as the main page
class JournalEntryViewAlt(
    TransactionsViewMixin, JournalEntryViewMixin, LoginRequiredMixin, View
):
    login_url = "/login/"
    redirect_field_name = "next"
    view_template = "api/views/journal-entry-view-alt.html"

    def get_table_html(self, transactions):
        print('get_table_html')
        transaction_ids = transactions.values_list('id', flat=True)
        transactions = list(transactions)  # Convert queryset to list
        transactions_with_next = [
            {
                "current": transactions[i], 
                "next": transactions[i+1] if i+1 < len(transactions) else None,
                "next_next": transactions[i+2] if i+2 < len(transactions) else None
            }
            for i in range(len(transactions))
        ]
        context = {
            "transactions": transactions_with_next,
            "transaction_ids": transaction_ids
        }

        table_template = "api/tables/transactions-table-alt.html"
        return render_to_string(table_template, context)
    
    def get(self, request):
        print('get')
        transactions = Transaction.objects.all().order_by('date')
        table_html = self.get_table_html(
            transactions=transactions
        )
        jei_form_html = get_journal_entry_form_html(transaction=transactions[0], transaction_ids=transactions.values_list('id', flat=True))
        context = {
            "table": table_html,
            "form": jei_form_html
        }

        html = render_to_string(self.view_template, context)
        return HttpResponse(html)