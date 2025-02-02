from django.forms import modelformset_factory
from django.http import HttpResponse
from django.template.loader import render_to_string

from api.forms import (
    BaseJournalEntryItemFormset,
    JournalEntryItemForm,
    JournalEntryMetadataForm,
)
from api.models import JournalEntry, JournalEntryItem, Paystub, PaystubValue, S3File


class JournalEntryViewMixin:
    entry_form_template = "api/entry_forms/journal-entry-item-form.html"

    def get_paystubs_table_html(self):
        # Make sure endpoint doesn't return a table until all S3files have paystubs
        oustanding_textract_jobs = S3File.objects.filter(analysis_complete__isnull=True)
        if oustanding_textract_jobs:
            return render_to_string("api/tables/paystubs-table-poller.html")

        paystubs = (
            Paystub.objects.filter(journal_entry__isnull=True)
            .prefetch_related("paystub_values")
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
    ):

        if not transaction:
            return ""

        context = {}

        if not (debit_formset and credit_formset):
            try:
                journal_entry = transaction.journal_entry
                journal_entry_items = JournalEntryItem.objects.filter(
                    journal_entry=journal_entry
                )
                journal_entry_debits = journal_entry_items.filter(
                    type=JournalEntryItem.JournalEntryType.DEBIT
                )
                journal_entry_credits = journal_entry_items.filter(
                    type=JournalEntryItem.JournalEntryType.CREDIT
                )
                bound_debits_count = journal_entry_debits.count()
                bound_credits_count = journal_entry_credits.count()
            except JournalEntry.DoesNotExist:
                bound_debits_count = 0
                bound_credits_count = 0
                journal_entry_debits = JournalEntryItem.objects.none()
                journal_entry_credits = JournalEntryItem.objects.none()

            debits_initial_data = []
            credits_initial_data = []

            if transaction.amount >= 0:
                is_debit = True
            else:
                is_debit = False

            prefill_debits_count = 0
            prefill_credits_count = 0
            if bound_debits_count + bound_credits_count == 0:
                primary_account, secondary_account = (
                    (transaction.account, transaction.suggested_account)
                    if is_debit
                    else (transaction.suggested_account, transaction.account)
                )
                primary_entity, secondary_entity = (
                    (transaction.account.entity, transaction.suggested_entity)
                    if is_debit
                    else (transaction.suggested_entity, transaction.account.entity)
                )

                debits_initial_data.append(
                    {
                        "account": getattr(primary_account, "name", None),
                        "amount": abs(transaction.amount),
                        "entity": primary_entity,
                    }
                )

                credits_initial_data.append(
                    {
                        "account": getattr(secondary_account, "name", None),
                        "amount": abs(transaction.amount),
                        "entity": secondary_entity,
                    }
                )

                if transaction.prefill:
                    prefill_items = transaction.prefill.prefillitem_set.all().order_by(
                        "order"
                    )
                    for item in prefill_items:
                        if (
                            item.journal_entry_item_type
                            == JournalEntryItem.JournalEntryType.DEBIT
                        ):
                            debits_initial_data.append(
                                {
                                    "account": item.account.name,
                                    "amount": 0,
                                    "entity": item.entity.name,
                                }
                            )
                            prefill_debits_count += 1
                        else:
                            credits_initial_data.append(
                                {
                                    "account": item.account.name,
                                    "amount": 0,
                                    "entity": item.entity.name,
                                }
                            )
                            prefill_credits_count += 1

                if paystub_id:
                    paystub_values = PaystubValue.objects.filter(
                        paystub__pk=paystub_id
                    ).select_related("account")
                    debits_initial_data = []
                    credits_initial_data = []
                    prefill_debits_count = 0
                    prefill_credits_count = 0
                    for paystub_value in paystub_values:
                        if (
                            paystub_value.journal_entry_item_type
                            == JournalEntryItem.JournalEntryType.DEBIT
                        ):
                            debits_initial_data.append(
                                {
                                    "account": paystub_value.account.name,
                                    "amount": paystub_value.amount,
                                    "entity": paystub_value.entity,
                                }
                            )
                            prefill_debits_count += 1
                        else:
                            credits_initial_data.append(
                                {
                                    "account": paystub_value.account.name,
                                    "amount": paystub_value.amount,
                                    "entity": paystub_value.entity,
                                }
                            )
                            prefill_credits_count += 1

            debit_formset = modelformset_factory(
                JournalEntryItem,
                form=JournalEntryItemForm,
                formset=BaseJournalEntryItemFormset,
                extra=max((10 - bound_debits_count), prefill_debits_count),
            )
            credit_formset = modelformset_factory(
                JournalEntryItem,
                form=JournalEntryItemForm,
                formset=BaseJournalEntryItemFormset,
                extra=max((10 - bound_credits_count), prefill_credits_count),
            )

            debit_formset = debit_formset(
                queryset=journal_entry_debits,
                initial=debits_initial_data,
                prefix="debits",
            )
            credit_formset = credit_formset(
                queryset=journal_entry_credits,
                initial=credits_initial_data,
                prefix="credits",
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
        }

        return render_to_string(self.entry_form_template, context)
