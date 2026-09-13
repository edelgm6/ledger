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


def render_paystubs_table(data: PaystubsTableData, show_fill_button: bool = True) -> str:
    """
    Renders the paystubs table HTML.

    Shows a poller if any Textract jobs are still processing,
    otherwise shows unlinked paystubs.

    Args:
        data: PaystubsTableData containing has_pending_jobs flag and paystubs list.
        show_fill_button: Whether row-click detail should include the Fill Paystub button.
    """
    if data.has_pending_jobs:
        return render_to_string(
            "api/tables/paystubs-table-poller.html",
            {
                "pending_files": data.pending_files,
                "has_active_jobs": data.has_active_jobs,
            },
        )

    return render_to_string(
        "api/tables/paystubs-table.html",
        {"paystubs": data.paystubs, "show_fill_button": show_fill_button},
    )


def render_paystubs_table_oob_swap(
    data: PaystubsTableData, show_fill_button: bool = True
) -> str:
    """Renders the paystubs table wrapped for an HTMX out-of-band swap into #paystubs."""
    table_html = render_paystubs_table(data, show_fill_button=show_fill_button)
    return render_to_string(
        "api/tables/paystubs-oob-wrapper.html",
        {"paystubs_table_html": table_html},
    )


def render_paystub_detail(data: PaystubDetailData, show_fill_button: bool = True) -> str:
    """
    Renders the paystub detail view HTML.

    Args:
        data: PaystubDetailData containing paystub_values and paystub_id.
        show_fill_button: Whether to render the Fill Paystub button.
    """
    return render_to_string(
        "api/tables/paystub-detail.html",
        {
            "paystub_values": data.paystub_values,
            "paystub_id": data.paystub_id,
            "show_fill_button": show_fill_button,
        },
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

    # Which column the source account lands in is purely a function of the
    # transaction's sign, so derive it once for both branches. It used to be
    # hard-coded True when bound formsets were supplied (i.e. after failed
    # validation), which sent focus to the already-prefilled column instead of
    # the one the user still has to fill in.
    #
    # Note the template reads this inverted: `autofocus_debit` true focuses the
    # CREDIT column, because a positive (income) transaction prefills the debit
    # side and the user completes the credit side.
    is_debit = transaction.amount >= 0

    # Build formsets if not provided. Test for absence explicitly: a formset's
    # truthiness is its form count, so a bound formset with zero forms is falsy
    # and would be silently replaced while its errors were still rendering.
    if debit_formset is None or credit_formset is None:
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


