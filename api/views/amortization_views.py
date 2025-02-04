from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views import View

from api.forms import AmortizationForm, DateForm
from api.models import Account, Amortization, JournalEntryItem


class AmortizationTableMixin:
    def get_amortization_table_html(self):
        amortizations = (
            Amortization.objects.select_related(
                "accrued_journal_entry_item__journal_entry__transaction",
                "suggested_account",
            )
            .filter(is_closed=False)
            .order_by("accrued_journal_entry_item__journal_entry__transaction__date")
        )

        for amortization in amortizations:
            remaining_balance, remaining_periods, latest_transaction_date = (
                amortization.get_remaining_balance_and_periods_and_max_date()
            )
            amortization.remaining_balance = remaining_balance
            amortization.remaining_periods = remaining_periods
            amortization.latest_transaction_date = latest_transaction_date
        return render_to_string(
            "api/tables/amortization-table.html", {"amortizations": amortizations}
        )

    def get_unattached_prepaids_table_html(self):
        prepaid_table_template = "api/tables/unattached-prepaids.html"

        # Get all JEIs where it's a prepaid expense account, there is no
        # existing amortization, and it's not part of an amortizing txn
        unattached_journal_entries = JournalEntryItem.objects.filter(
            account__special_type=Account.SpecialType.PREPAID_EXPENSES,
            amortization__isnull=True,
            journal_entry__transaction__amortization__isnull=True,
        ).select_related("journal_entry__transaction", "account")
        return render_to_string(
            prepaid_table_template, {"journal_entry_items": unattached_journal_entries}
        )

    def get_amortization_form_html(self, journal_entry_item=None):
        form = AmortizationForm()
        if journal_entry_item:
            form.initial["accrued_journal_entry_item"] = journal_entry_item
        form_template = "api/entry_forms/amortization-form.html"
        return render_to_string(form_template, {"form": form})

    def get_amortize_form_html(self, amortization):
        form_template = "api/entry_forms/amortize-form.html"
        transactions = amortization.get_related_transactions()
        context = {
            "transactions": transactions,
            "amortization": amortization,
            "date_form": DateForm(),
        }
        return render_to_string(form_template, context)


class AmortizeFormView(AmortizationTableMixin, LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, amortization_id):
        amortization = get_object_or_404(Amortization, pk=amortization_id)
        amortize_form_html = self.get_amortize_form_html(amortization)
        return HttpResponse(amortize_form_html)

    def post(self, request, amortization_id):
        amortization = get_object_or_404(Amortization, pk=amortization_id)
        form = DateForm(request.POST)
        if form.is_valid():
            amortization.amortize(form.cleaned_data["date"])

            context = {
                "table": self.get_amortization_table_html(),
                "amortization_form": self.get_amortize_form_html(amortization),
            }

            amortizations_content_template = "api/content/amortizations-content.html"
            html = render_to_string(amortizations_content_template, context)
            return HttpResponse(html)


class AmortizationFormView(AmortizationTableMixin, LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, journal_entry_item_id):
        journal_entry_item = get_object_or_404(
            JournalEntryItem, pk=journal_entry_item_id
        )
        amortization_form_html = self.get_amortization_form_html(journal_entry_item)
        return HttpResponse(amortization_form_html)


class AmortizationView(AmortizationTableMixin, LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"
    amortizations_content_template = "api/content/amortizations-content.html"
    unattached_transactions_content = "api/content/unattached-transactions-content.html"
    amortizations_content = "api/content/amortizations-content.html"

    def get(self, request, *args, **kwargs):

        # create amortizations
        unattached_transactions_html = self.get_unattached_prepaids_table_html()
        amortization_form_html = self.get_amortization_form_html()

        # amortize
        amortizations_table_html = self.get_amortization_table_html()

        context = {
            "unattached_transactions": render_to_string(
                self.unattached_transactions_content,
                {
                    "table": unattached_transactions_html,
                    "amortization_form": amortization_form_html,
                },
            ),
            "amortize": render_to_string(
                self.amortizations_content_template, {"table": amortizations_table_html}
            ),
        }

        template = "api/views/amortizations.html"
        return render(request, template, context)

    def post(self, request):
        form = AmortizationForm(request.POST)

        if form.is_valid():
            form.save()
            unattached_transactions_html = self.get_unattached_prepaids_table_html()
            amortization_form_html = self.get_amortization_form_html()

            # amortize
            amortizations_table_html = self.get_amortization_table_html()

            context = {
                "unattached_transactions": render_to_string(
                    self.unattached_transactions_content,
                    {
                        "table": unattached_transactions_html,
                        "amortization_form": amortization_form_html,
                    },
                ),
                "amortize": render_to_string(
                    self.amortizations_content_template,
                    {"table": amortizations_table_html},
                ),
            }

            template = "api/views/amortizations.html"
            return render(request, template, context)

        print(form.errors)
