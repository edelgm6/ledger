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
from api.services.journal_entry_services import (
    apply_autotags_to_open_transactions,
    get_accounts_choices,
    get_entities_choices,
    get_post_save_context,
    save_journal_entry,
    validate_journal_entry_balance,
)
from api.views.journal_entry_helpers import (
    extract_created_entities,
    render_journal_entry_form,
    render_paystubs_table,
)
from api.views.transaction_views import TransactionsViewMixin


class TriggerAutoTagView(LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request):
        count = apply_autotags_to_open_transactions()
        return HttpResponse(
            f"<small class=text-success>Autotag complete ({count} transactions)</small>"
        )


# Called every time the page is filtered
class JournalEntryTableView(TransactionsViewMixin, LoginRequiredMixin, View):
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
            entry_form_html = render_journal_entry_form(transaction=transaction)
            paystubs_table_html = render_paystubs_table()
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
class JournalEntryFormView(TransactionsViewMixin, LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"
    item_form_template = "api/entry_forms/journal-entry-item-form.html"

    def get(self, request, transaction_id):
        transaction = Transaction.objects.select_related("journal_entry").get(
            pk=transaction_id
        )
        paystub_id = request.GET.get("paystub_id")
        row_index = request.GET.get("row_index", 0)
        entry_form_html = render_journal_entry_form(
            transaction=transaction,
            index=int(row_index) if row_index else 0,
            paystub_id=paystub_id,
        )

        return HttpResponse(entry_form_html)


class PaystubTableView(LoginRequiredMixin, View):
    def get(self, request):
        html = render_paystubs_table()
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
class JournalEntryView(TransactionsViewMixin, LoginRequiredMixin, View):
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
        entry_form_html = render_journal_entry_form(transaction=transaction)
        paystubs_table_html = render_paystubs_table()
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
        """
        Saves journal entry for a transaction.

        Flow:
        1. Build and validate forms
        2. Validate business rules via service
        3. Save via service (atomic)
        4. Build response context via service
        5. Render response via helpers
        """
        # 1. Build forms
        transaction = get_object_or_404(Transaction, pk=transaction_id)

        JournalEntryItemFormset = modelformset_factory(
            JournalEntryItem,
            formset=BaseJournalEntryItemFormset,
            form=JournalEntryItemForm,
        )

        accounts_choices = get_accounts_choices()
        entities_choices = get_entities_choices()

        debit_formset = JournalEntryItemFormset(
            request.POST,
            prefix="debits",
            form_kwargs={
                "open_accounts_choices": accounts_choices,
                "open_entities_choices": entities_choices,
            },
        )
        credit_formset = JournalEntryItemFormset(
            request.POST,
            prefix="credits",
            form_kwargs={
                "open_accounts_choices": accounts_choices,
                "open_entities_choices": entities_choices,
            },
        )
        metadata_form = JournalEntryMetadataForm(request.POST)

        # 2. Validate forms (field-level)
        if not (
            debit_formset.is_valid()
            and credit_formset.is_valid()
            and metadata_form.is_valid()
        ):
            # Render form with field errors
            entry_form_html = render_journal_entry_form(
                transaction=transaction,
                debit_formset=debit_formset,
                credit_formset=credit_formset,
                form_errors=[],
            )
            response = HttpResponse(entry_form_html)
            response.headers["HX-Retarget"] = "#form-div"
            return response

        # 3. Validate business rules
        validation_result = validate_journal_entry_balance(
            transaction=transaction,
            debits_data=debit_formset.cleaned_data,
            credits_data=credit_formset.cleaned_data,
        )

        if not validation_result.is_valid:
            # Render form with validation errors
            entry_form_html = render_journal_entry_form(
                transaction=transaction,
                debit_formset=debit_formset,
                credit_formset=credit_formset,
                form_errors=validation_result.errors,
            )
            response = HttpResponse(entry_form_html)
            response.headers["HX-Retarget"] = "#form-div"
            return response

        # 4. Save (service handles ALL database operations)
        save_result = save_journal_entry(
            transaction_obj=transaction,
            debits_data=debit_formset.cleaned_data,
            credits_data=credit_formset.cleaned_data,
            paystub_id=metadata_form.cleaned_data.get("paystub_id"),
        )

        if not save_result.success:
            # This should rarely happen (validation passed)
            return HttpResponse(f"Error: {save_result.error}", status=500)

        # 5. Build response context via service
        filter_form = TransactionFilterForm(request.POST, prefix="filter")
        current_index = metadata_form.cleaned_data["index"]

        context = get_post_save_context(
            filter_form=filter_form,
            current_index=current_index,
            debit_formset=debit_formset,
            credit_formset=credit_formset,
        )

        # 6. Render response via helpers
        if context.highlighted_transaction:
            entry_form_html = render_journal_entry_form(
                transaction=context.highlighted_transaction,
                index=context.highlighted_index,
                created_entities=context.created_entities,
            )
        else:
            entry_form_html = ""

        table_html = self.get_table_html(
            transactions=context.transactions,
            index=context.highlighted_index,
            row_url=reverse("journal-entries"),
        )
        paystubs_table_html = render_paystubs_table()

        html = render_to_string(
            self.view_template,
            {
                "table": table_html,
                "entry_form": entry_form_html,
                "index": context.highlighted_index,
                "transaction_id": context.highlighted_transaction.pk
                if context.highlighted_transaction
                else None,
                "paystubs_table": paystubs_table_html,
            },
        )

        return HttpResponse(html)
