"""
Transaction views for HTTP orchestration.

Views handle HTTP requests/responses only, delegating business logic to
services and rendering to helpers.
"""

from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.views import View

from api import utils
from api.forms import TransactionFilterForm, TransactionForm, TransactionLinkForm
from api.models import Transaction
from api.services import transaction_services
from api.views import transaction_helpers


# ------------------Transactions View-----------------------


# Called by the filter form
class TransactionContentView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        # Parse and validate filter form
        form = TransactionFilterForm(request.GET, prefix="filter")
        if form.is_valid():
            transactions = form.get_transactions()
        else:
            transactions = []

        # Render via helpers
        form_html = transaction_helpers.render_transaction_form()
        row_url = reverse("transactions")
        table_html = transaction_helpers.render_transaction_table(
            transactions=transactions,
            no_highlight=True,
            row_url=row_url
        )

        # Combine content
        html = transaction_helpers.render_transactions_content(
            table_html=table_html,
            form_html=form_html
        )

        return HttpResponse(html)


# Called by table rows
class TransactionFormView(LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, transaction_id=None):
        transaction = get_object_or_404(Transaction, pk=transaction_id)
        form_html = transaction_helpers.render_transaction_form(
            transaction=transaction
        )
        return HttpResponse(form_html)


# Called to load page or POST new objects
class TransactionsView(LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request):
        # Calculate default date range (last month)
        last_two_months_last_days = utils.get_last_days_of_month_tuples()[0:2]
        last_day_of_last_month = last_two_months_last_days[0][0]
        first_day_of_last_month = last_two_months_last_days[1][0] + timedelta(days=1)

        # Filter transactions via service
        filter_result = transaction_services.filter_transactions(
            date_from=first_day_of_last_month,
            date_to=last_day_of_last_month,
            is_closed=False,
        )

        # Render filter form
        filter_form_html = transaction_helpers.render_transaction_filter_form(
            date_from=transaction_helpers.format_date_for_form(first_day_of_last_month),
            date_to=transaction_helpers.format_date_for_form(last_day_of_last_month),
            is_closed=False,
            get_url=reverse("transactions-content"),
        )

        # Render table and form
        row_url = reverse("transactions")
        table_html = transaction_helpers.render_transaction_table(
            transactions=filter_result.transactions,
            no_highlight=True,
            row_url=row_url
        )
        transaction_form_html = transaction_helpers.render_transaction_form()

        # Combine all HTML
        context = {
            "filter_form": filter_form_html,
            "table_and_form": transaction_helpers.render_transactions_content(
                table_html=table_html,
                form_html=transaction_form_html
            ),
        }

        view_template = "api/views/transactions.html"
        html = render_to_string(view_template, context)
        return HttpResponse(html)

    def post(self, request, transaction_id=None):
        # Parse filter form to get current transaction list
        filter_form = TransactionFilterForm(request.POST, prefix="filter")
        if filter_form.is_valid():
            transactions = list(filter_form.get_transactions())
        else:
            print(filter_form.errors)
            transactions = []

        # Handle different actions
        action = request.POST.get("action")
        transaction_obj = None

        if action == "delete":
            # Delete via service
            result = transaction_services.delete_transaction(transaction_id)
            if result.success:
                transaction_obj = result.transaction
                form_html = transaction_helpers.render_transaction_form(
                    created_transaction=transaction_obj,
                    change="delete"
                )
            else:
                return HttpResponse(result.error, status=400)

        elif action == "clear":
            # Clear form
            form_html = transaction_helpers.render_transaction_form()

        else:
            # Create or update transaction
            if transaction_id:
                transaction_obj = get_object_or_404(Transaction, pk=transaction_id)
                form = TransactionForm(request.POST, instance=transaction_obj)
                change = "update"
            else:
                form = TransactionForm(request.POST)
                change = "create"

            if form.is_valid():
                transaction_obj = form.save()
                form_html = transaction_helpers.render_transaction_form(
                    created_transaction=transaction_obj,
                    change=change
                )
            else:
                # Return form with errors
                return HttpResponse("Form validation failed", status=400)

        # Render updated table
        row_url = reverse("transactions")
        table_html = transaction_helpers.render_transaction_table(
            transactions=transactions,
            no_highlight=True,
            row_url=row_url
        )

        # Combine and return
        html = transaction_helpers.render_transactions_content(
            table_html=table_html,
            form_html=form_html,
            transaction=transaction_obj
        )

        return HttpResponse(html)


# ------------------Linking View-----------------------


# Called on filter
class LinkTransactionsContentView(LoginRequiredMixin, View):

    def get(self, request):
        # Parse and validate filter form
        form = TransactionFilterForm(request.GET, prefix="filter")
        if form.is_valid():
            transactions = list(form.get_transactions())
        else:
            transactions = []

        # Render via helpers
        table_html = transaction_helpers.render_transaction_table(
            transactions,
            no_highlight=True,
            double_row_click=True
        )
        link_form_html = transaction_helpers.render_transaction_link_form()

        # Combine content
        html = transaction_helpers.render_transactions_link_content(
            table_html=table_html,
            link_form_html=link_form_html
        )

        return HttpResponse(html)


# Called to load page and link transactions
class LinkTransactionsView(LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request):
        # Filter for linkable transactions
        filter_result = transaction_services.filter_transactions(
            is_closed=False,
            has_linked_transaction=False,
            transaction_types=[
                Transaction.TransactionType.TRANSFER,
                Transaction.TransactionType.PAYMENT,
            ],
        )

        # Render filter form
        filter_form_html = transaction_helpers.render_transaction_filter_form(
            is_closed=False,
            has_linked_transaction=False,
            transaction_type=[
                Transaction.TransactionType.TRANSFER,
                Transaction.TransactionType.PAYMENT,
            ],
            get_url=reverse("link-transactions-content"),
        )

        # Render table and link form
        table_html = transaction_helpers.render_transaction_table(
            filter_result.transactions,
            no_highlight=True,
            double_row_click=True
        )
        link_form_html = transaction_helpers.render_transaction_link_form()

        # Combine all HTML
        context = {
            "filter_form": filter_form_html,
            "table_and_form": transaction_helpers.render_transactions_link_content(
                table_html=table_html,
                link_form_html=link_form_html
            ),
        }

        view_template = "api/views/transactions-linking.html"
        html = render_to_string(view_template, context)
        return HttpResponse(html)

    def post(self, request):
        # Parse link form
        form = TransactionLinkForm(request.POST)

        # Link transactions if form valid
        if form.is_valid():
            form.save()  # TransactionLinkForm handles the linking logic
        else:
            print(form.errors)
            print(form.non_field_errors())

        # Re-query transactions AFTER linking so linked/closed ones are excluded
        filter_form = TransactionFilterForm(request.POST, prefix="filter")
        if filter_form.is_valid():
            transactions = list(filter_form.get_transactions())
        else:
            transactions = []

        # Render updated table and form
        table_html = transaction_helpers.render_transaction_table(
            transactions=transactions,
            no_highlight=True,
            double_row_click=True
        )
        link_form_html = transaction_helpers.render_transaction_link_form()

        html = transaction_helpers.render_transactions_link_content(
            table_html=table_html,
            link_form_html=link_form_html
        )

        return HttpResponse(html)
