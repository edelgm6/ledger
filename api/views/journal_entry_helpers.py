"""
Helper functions for rendering journal entry HTML.

These pure functions replace the JournalEntryViewMixin, extracting
rendering logic into testable, reusable functions.
"""

from typing import List, Optional

from django.template.loader import render_to_string

from api.forms import JournalEntryMetadataForm, TransactionFilterForm
from api.models import Entity, Transaction
from api.services.journal_entry_services import (
    get_debits_and_credits,
    get_formsets,
    get_initial_data,
)
from api.services.paystub_services import PaystubDetailData, PaystubsTableData


def render_paystubs_table(data: PaystubsTableData) -> str:
    """
    Renders the paystubs table HTML.

    Shows a poller if any Textract jobs are still processing,
    otherwise shows unlinked paystubs.

    Args:
        data: PaystubsTableData containing has_pending_jobs flag and paystubs list.
    """
    if data.has_pending_jobs:
        return render_to_string(
            "api/tables/paystubs-table-poller.html",
            {"pending_files": data.pending_files},
        )

    return render_to_string("api/tables/paystubs-table.html", {"paystubs": data.paystubs})


def render_paystub_detail(data: PaystubDetailData) -> str:
    """
    Renders the paystub detail view HTML.

    Args:
        data: PaystubDetailData containing paystub_values and paystub_id.
    """
    return render_to_string(
        "api/tables/paystub-detail.html",
        {"paystub_values": data.paystub_values, "paystub_id": data.paystub_id},
    )


def render_journal_entry_form(
    transaction: Optional[Transaction],
    index: int = 0,
    paystub_id: Optional[int] = None,
    created_entities: Optional[List[Entity]] = None,
    debit_formset=None,
    credit_formset=None,
    form_errors: Optional[List[str]] = None,
) -> str:
    """
    Renders the journal entry form HTML.

    If formsets are not provided, builds them from transaction data.
    Can optionally prefill from paystub or show validation errors.
    """
    if not transaction:
        return ""

    # Source-account polarity decides which column the user lands in:
    # debit-source transaction → credit column needs the offsetting entry, focus there.
    autofocus_credit = transaction.amount >= 0

    # Build formsets if not provided
    if not (debit_formset and credit_formset):
        journal_entry_debits, journal_entry_credits = get_debits_and_credits(transaction)
        bound_debits_count = journal_entry_debits.count()
        bound_credits_count = journal_entry_credits.count()

        if bound_debits_count + bound_credits_count == 0:
            debits_initial_data, credits_initial_data = get_initial_data(
                transaction=transaction, paystub_id=paystub_id
            )
        else:
            debits_initial_data = []
            credits_initial_data = []

        debit_formset, credit_formset = get_formsets(
            debits_initial_data=debits_initial_data,
            credits_initial_data=credits_initial_data,
            journal_entry_debits=journal_entry_debits,
            journal_entry_credits=journal_entry_credits,
            bound_debits_count=bound_debits_count,
            bound_credits_count=bound_credits_count,
        )

    metadata_form = JournalEntryMetadataForm(initial={"index": index, "paystub_id": paystub_id})

    context = {
        "debit_formset": debit_formset,
        "credit_formset": credit_formset,
        "transaction_id": transaction.id,
        "autofocus_credit": autofocus_credit,
        "form_errors": form_errors or [],
        "debit_prefilled_total": debit_formset.get_entry_total(),
        "credit_prefilled_total": credit_formset.get_entry_total(),
        "metadata_form": metadata_form,
        "created_entities": created_entities,
    }

    return render_to_string("api/entry_forms/journal-entry-rapidfire-form.html", context)


def render_journal_entry_filter_form(
    is_closed: Optional[bool] = None,
    has_linked_transaction: Optional[bool] = None,
    transaction_type: Optional[List[str]] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    get_url: Optional[str] = None,
) -> str:
    """Renders the JE-only sepia filter form HTML."""
    form = TransactionFilterForm(prefix="filter")
    form.initial["is_closed"] = is_closed
    form.initial["has_linked_transaction"] = has_linked_transaction
    form.initial["transaction_type"] = transaction_type
    form.initial["date_from"] = date_from
    form.initial["date_to"] = date_to

    return render_to_string(
        "api/filter_forms/journal-entry-filter-form.html",
        {"filter_form": form, "get_url": get_url},
    )


def render_journal_entry_transactions_table(
    transactions,
    index: int = 0,
    no_highlight: bool = False,
    row_url: Optional[str] = None,
) -> str:
    """Renders the JE-only sepia transactions table HTML."""
    return render_to_string(
        "api/tables/journal-entry-transactions-table.html",
        {
            "transactions": transactions,
            "index": index,
            "no_highlight": no_highlight,
            "row_url": row_url,
        },
    )


def render_journal_entry_paystubs_table(data: PaystubsTableData) -> str:
    """Renders the JE-only sepia paystubs table HTML."""
    if data.has_pending_jobs:
        return render_to_string(
            "api/tables/paystubs-table-poller.html",
            {"pending_files": data.pending_files},
        )

    return render_to_string(
        "api/tables/journal-entry-paystubs-table.html",
        {"paystubs": data.paystubs},
    )
