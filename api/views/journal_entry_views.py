from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.views import View

from api.forms import (
    JournalEntryMetadataForm,
    TransactionFilterForm,
)
from api.models import Transaction
from api.services.journal_entry_services import (
    apply_autotags_to_open_transactions,
    get_accounts_choices,
    get_entities_choices,
    get_journal_entry_item_formset,
    get_post_save_context,
    save_journal_entry,
    validate_journal_entry_balance,
)
from api.services.paystub_services import (
    get_paystub_detail_data,
    get_paystubs_table_data,
)
from api.services.paystub_upload_services import retry_paystub_processing
from api.views.journal_entry_helpers import (
    render_journal_entry_form,
    render_paystub_detail,
    render_paystubs_table,
)
from api.views import transaction_helpers
from api.views.page_utils import render_action_status, render_full_page


class TriggerAutoTagView(LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request):
        count = apply_autotags_to_open_transactions()
        return HttpResponse(render_action_status("Autotag complete", count))


JOURNAL_ENTRY_PAGE_TEMPLATE = "api/views/journal-entry-view.html"


def _render_journal_entry_page(
    transactions,
    transaction,
    index=0,
    created_entities=None,
    **extra,
) -> str:
    """Assembles the journal-entry page: table + entry form + paystubs table.

    Three handlers built this same five-key context and made the same three
    render calls, so adding a key meant remembering all three. Which row is
    selected is *not* folded in -- the filter path takes the first row, the
    save path takes the row its service computed -- so each caller still
    decides that and passes it here.
    """
    table_html = transaction_helpers.render_transaction_table(
        transactions=transactions,
        index=index,
        row_url=reverse("journal-entries"),
    )
    entry_form_html = (
        render_journal_entry_form(
            transaction=transaction,
            index=index,
            created_entities=created_entities,
        )
        if transaction is not None
        else ""
    )
    context = {
        "entry_form": entry_form_html,
        "table": table_html,
        "paystubs_table": render_paystubs_table(get_paystubs_table_data()),
        "transaction_id": transaction.id if transaction else None,
        "index": index,
    }
    # The full page load adds filter_form and is_initial_load; the HTMX
    # fragments do not.
    context.update(extra)
    return render_to_string(JOURNAL_ENTRY_PAGE_TEMPLATE, context)


# Called every time the page is filtered
class JournalEntryTableView(LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, *args, **kwargs):
        form = TransactionFilterForm(request.GET, prefix="filter")
        if form.is_valid():
            transactions = form.get_transactions()
            # The filter path selects the first row.
            transaction = transactions[0] if transactions else None
            return HttpResponse(
                _render_journal_entry_page(transactions, transaction)
            )

        # An invalid filter form used to fall through and return None (a 500).
        # Render the page with an empty result set instead.
        return HttpResponse(_render_journal_entry_page([], None))


# Called every time a table row is clicked
class JournalEntryFormView(LoginRequiredMixin, View):
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
        paystubs_table_data = get_paystubs_table_data()
        html = render_paystubs_table(paystubs_table_data)
        return HttpResponse(html)


class PaystubRetryView(LoginRequiredMixin, View):
    def post(self, request, s3file_id):
        retry_paystub_processing(s3file_id)
        html = render_paystubs_table(get_paystubs_table_data())
        return HttpResponse(html)


class PaystubDetailView(LoginRequiredMixin, View):

    def get(self, request, paystub_id):
        detail_data = get_paystub_detail_data(paystub_id)
        show_fill_button = request.GET.get("show_fill_button") == "true"
        html = render_paystub_detail(detail_data, show_fill_button=show_fill_button)
        return HttpResponse(html)


# Called as the main page
class JournalEntryView(LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request):
        # Collect HTML for all components in view
        from api.services import transaction_services

        filter_result = transaction_services.filter_transactions(
            is_closed=False,
            transaction_types=[
                Transaction.TransactionType.INCOME,
                Transaction.TransactionType.PURCHASE,
            ],
            suggested_first=True,
        )
        transactions = filter_result.transactions

        filter_form_html = transaction_helpers.render_transaction_filter_form(
            is_closed=False,
            transaction_type=[
                Transaction.TransactionType.INCOME,
                Transaction.TransactionType.PURCHASE,
            ],
            get_url=reverse("journal-entries-table"),
            suggested_first=True,
        )
        # Like the filter path, the initial load selects the first row.
        transaction = transactions[0] if transactions else None
        html = _render_journal_entry_page(
            transactions,
            transaction,
            filter_form=filter_form_html,
            is_initial_load=True,
        )
        return render_full_page(request, html)

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

        JournalEntryItemFormset = get_journal_entry_item_formset()

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

        # Preserve paystub linkage and row index across error re-renders so a
        # validation failure doesn't disassociate the form from its paystub.
        submitted_paystub_id = request.POST.get("paystub_id") or None
        try:
            submitted_index = int(request.POST.get("index") or 0)
        except ValueError:
            submitted_index = 0

        # 2. Validate forms (field-level)
        if not (
            debit_formset.is_valid()
            and credit_formset.is_valid()
            and metadata_form.is_valid()
        ):
            # Render form with field errors
            entry_form_html = render_journal_entry_form(
                transaction=transaction,
                index=submitted_index,
                paystub_id=submitted_paystub_id,
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
                index=submitted_index,
                paystub_id=submitted_paystub_id,
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
        # The save path selects whichever row its service computed.
        return HttpResponse(
            _render_journal_entry_page(
                context.transactions,
                context.highlighted_transaction,
                index=context.highlighted_index,
                created_entities=context.created_entities,
            )
        )
