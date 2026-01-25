"""
Helper functions for rendering journal entry HTML.

These pure functions replace the JournalEntryViewMixin, extracting
rendering logic into testable, reusable functions.
"""

from typing import List, Optional

from django.template.loader import render_to_string

from api.forms import JournalEntryMetadataForm
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
        return render_to_string("api/tables/paystubs-table-poller.html")

    return render_to_string("api/tables/paystubs-table.html", {"paystubs": data.paystubs})


def render_paystub_detail(data: PaystubDetailData) -> str:
    """
    Renders the paystub detail view HTML.

    Args:
        data: PaystubDetailData containing paystub_values and paystub_id.
    """
    return render_to_string(
        "api/tables/paystubs-table.html",
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

    # Build formsets if not provided
    if not (debit_formset and credit_formset):
        journal_entry_debits, journal_entry_credits = get_debits_and_credits(transaction)
        bound_debits_count = journal_entry_debits.count()
        bound_credits_count = journal_entry_credits.count()

        # Determine if transaction's source account is a debit
        is_debit = transaction.amount >= 0

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
    else:
        is_debit = True  # Default if formsets provided with errors

    # Build metadata form
    metadata = {"index": index, "paystub_id": paystub_id}
    metadata_form = JournalEntryMetadataForm(initial=metadata)

    # Calculate totals
    debit_prefilled_total = debit_formset.get_entry_total()
    credit_prefilled_total = credit_formset.get_entry_total()

    context = {
        "debit_formset": debit_formset,
        "credit_formset": credit_formset,
        "transaction_id": transaction.id,
        "autofocus_debit": is_debit,
        "form_errors": form_errors or [],
        "debit_prefilled_total": debit_prefilled_total,
        "credit_prefilled_total": credit_prefilled_total,
        "metadata_form": metadata_form,
        "created_entities": created_entities,
    }

    return render_to_string("api/entry_forms/journal-entry-item-form.html", context)


def extract_created_entities(formsets) -> List[Entity]:
    """
    Extracts entities that were created during form cleaning.

    Forms create entities on-the-fly if user enters a new entity name.
    This helper collects them to pass to the next form render.
    """
    created_entities = []
    for formset in formsets:
        for form in formset:
            if hasattr(form, 'created_entity'):
                created_entities.append(form.created_entity)
    return created_entities
