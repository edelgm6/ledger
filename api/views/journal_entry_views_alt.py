from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.views import View

from api.models import Transaction
from api.views.mixins import JournalEntryViewMixin
from api.views.transaction_views import TransactionsViewMixin


class JournalEntryUpdate(View):
    
    def post(self, request, transaction_id):
        response = HttpResponse()
        response["HX-Trigger"] = "afterOnload"
        return response

class JournalEntryButton(View):
    
    def get(self, request, transaction_id):
        template = "api/entry_forms/journal-entry-button.html"
        context = {
            "transaction_id": transaction_id,
            "next_transaction_id": request.GET.get("next_transaction_id")
        }
        html = render_to_string(template, context)
        return HttpResponse(html)

# Called as the main page
class JournalEntryViewAlt(
    TransactionsViewMixin, JournalEntryViewMixin, LoginRequiredMixin, View
):
    login_url = "/login/"
    redirect_field_name = "next"
    view_template = "api/views/journal-entry-view-alt.html"

    def get_table_html(self, transactions):
        transactions = list(transactions)  # Convert queryset to list
        transactions_with_next = [
            {"current": transactions[i], "next": transactions[i+1] if i+1 < len(transactions) else None}
            for i in range(len(transactions))
        ]
        context = {
            "transactions": transactions_with_next,
        }

        table_template = "api/tables/transactions-table-alt.html"
        return render_to_string(table_template, context)
    
    def get(self, request):
        transactions = Transaction.objects.all()
        table_html = self.get_table_html(
            transactions=transactions
        )
        context = {
            "table": table_html
        }

        html = render_to_string(self.view_template, context)
        return HttpResponse(html)