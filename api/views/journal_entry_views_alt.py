from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.views import View

from api.models import Transaction
from api.services.journal_entry_services import get_journal_entry_form_html
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
        print(request.POST)
        # TODO: Process the post

        next_transaction_id = request.GET.get("next_transaction_id")
        next_next_transaction_id = request.GET.get("next_transaction_id")
        transaction = Transaction.objects.get(pk=next_transaction_id)
        html = get_journal_entry_form_html(transaction, next_transaction_id, next_next_transaction_id)

        response = HttpResponse(html)
        response["HX-Trigger"] = "afterOnload"

        return response

class JournalEntryButton(View):
    
    def get(self, request, transaction_id):
        print('journalentrybutton')
        print(request.GET.get('transaction_ids'))
        print(request.GET.dict())
        if not transaction_id:
            return ""
        
        transaction_ids = request.GET.get('transaction_ids')
        transaction_ids = transaction_ids.split(',')

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
        transactions = Transaction.objects.all()
        table_html = self.get_table_html(
            transactions=transactions
        )
        jei_form_html = get_journal_entry_form_html(transaction=transactions[0], transaction_ids=transactions.values_list('id', flat=True))
        context = {
            "table": table_html,
            "form": jei_form_html,
            "transaction_ids": transactions.values_list('id', flat=True)
        }

        html = render_to_string(self.view_template, context)
        return HttpResponse(html)