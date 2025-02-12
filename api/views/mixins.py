from typing import List

from django.forms import BaseModelFormSet
from django.http import HttpResponse
from django.template.loader import render_to_string

from api.forms import (
    JournalEntryMetadataForm,
)
from api.models import (
    Entity,
    Paystub,
    S3File,
)
from api.services.journal_entry_services import (
    get_debits_and_credits,
    get_formsets,
    get_initial_data,
)


class JournalEntryViewMixin:
    entry_form_template = "api/entry_forms/journal-entry-item-form.html"

    def get_created_entities(self, formsets: List[BaseModelFormSet]) -> List[Entity]:
        created_entities = []
        for formset in formsets:
            for form in formset:
                try:
                    created_entities.append(form.created_entity)
                except AttributeError:
                    continue

        return created_entities

    def get_paystubs_table_html(self):
        # Make sure endpoint doesn't return a table until all S3files have paystubs
        oustanding_textract_jobs = S3File.objects.filter(analysis_complete__isnull=True)
        if oustanding_textract_jobs:
            return render_to_string("api/tables/paystubs-table-poller.html")

        paystubs = (
            Paystub.objects.filter(journal_entry__isnull=True)
            .select_related("document")
            .order_by("title")
        )
        paystubs_template = "api/tables/paystubs-table.html"
        return render_to_string(paystubs_template, {"paystubs": paystubs})

    def get_combined_formset_errors(self, debit_formset, credit_formset):
        form_errors = []
        debit_total = debit_formset.get_entry_total()
        credit_total = credit_formset.get_entry_total()
        if debit_total != credit_total:
            form_errors.append(
                "Debits ($"
                + str(debit_total)
                + ") and Credits ($"
                + str(credit_total)
                + ") must balance."
            )

        print(form_errors)
        return form_errors

    def check_for_errors(
        self, request, debit_formset, credit_formset, metadata_form, transaction
    ):
        has_errors = False
        form_errors = []
        # Check if formsets have errors on their own, then check if they have errors
        # in the aggregate (e.g., don't have balanced credits/debits)
        if (
            debit_formset.is_valid()
            and credit_formset.is_valid()
            and metadata_form.is_valid()
        ):
            form_errors = self.get_combined_formset_errors(
                debit_formset=debit_formset, credit_formset=credit_formset
            )
            has_errors = bool(form_errors)
        else:
            print(debit_formset.errors)
            print(credit_formset.errors)
            print(metadata_form.errors)
            has_errors = True

        if not has_errors:
            return False, None

        context = {
            "debit_formset": debit_formset,
            "credit_formset": credit_formset,
            "transaction_id": transaction.id,
            "autofocus_debit": True,
            "form_errors": form_errors,
            "prefilled_total": debit_formset.get_entry_total(),
            "debit_prefilled_total": debit_formset.get_entry_total(),
            "credit_prefilled_total": credit_formset.get_entry_total(),
            "metadata_form": metadata_form,
        }

        html = render_to_string(self.entry_form_template, context)
        response = HttpResponse(html)
        response.headers["HX-Retarget"] = "#form-div"
        return True, response

    def get_journal_entry_form_html(
        self,
        transaction,
        index=0,
        debit_formset=None,
        credit_formset=None,
        is_debit=True,
        form_errors=None,
        paystub_id=None,
        created_entities=None,
    ):

        # If no transaction passed in, return nothing
        if not transaction:
            return ""

        # If didn't pass in formsets, create them
        if not (debit_formset and credit_formset):
            journal_entry_debits, journal_entry_credits = get_debits_and_credits(
                transaction
            )
            bound_debits_count = journal_entry_debits.count()
            bound_credits_count = journal_entry_credits.count()

            # Determine if transaction's source account is a debit
            if transaction.amount >= 0:
                is_debit = True
            else:
                is_debit = False

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

        metadata = {"index": index, "paystub_id": paystub_id}
        metadata_form = JournalEntryMetadataForm(initial=metadata)
        # Set the total amounts for the debit and credits
        debit_prefilled_total = debit_formset.get_entry_total()
        credit_prefilled_total = credit_formset.get_entry_total()
        context = {
            "debit_formset": debit_formset,
            "credit_formset": credit_formset,
            "transaction_id": transaction.id,
            "autofocus_debit": is_debit,
            "form_errors": form_errors,
            "debit_prefilled_total": debit_prefilled_total,
            "credit_prefilled_total": credit_prefilled_total,
            "metadata_form": metadata_form,
            "created_entities": created_entities,
        }

        return render_to_string(self.entry_form_template, context)
