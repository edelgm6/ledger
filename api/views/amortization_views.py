from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views import View

from api.forms import AmortizationForm, DateForm, DepreciationForm
from api.models import Account, Amortization, JournalEntryItem


class AmortizationTableMixin:
    amortizations_content_template = "api/content/amortizations-content.html"
    unattached_transactions_content = "api/content/unattached-transactions-content.html"
    unattached_depreciable_assets_content = (
        "api/content/unattached-depreciable-assets-content.html"
    )
    page_template = "api/views/amortizations.html"

    def render_page(self, request):
        context = {
            "unattached_transactions": render_to_string(
                self.unattached_transactions_content,
                {
                    "table": self.get_unattached_prepaids_table_html(),
                    "amortization_form": self.get_amortization_form_html(),
                },
            ),
            "unattached_depreciable_assets": render_to_string(
                self.unattached_depreciable_assets_content,
                {
                    "table": self.get_unattached_depreciable_assets_table_html(),
                    "depreciation_form": self.get_depreciation_form_html(),
                },
            ),
            "amortize": render_to_string(
                self.amortizations_content_template,
                {"table": self.get_amortization_table_html()},
            ),
        }
        return render(request, self.page_template, context)

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

    def get_unattached_depreciable_assets_table_html(self):
        table_template = "api/tables/unattached-depreciable-assets.html"

        unattached_journal_entries = (
            JournalEntryItem.objects.filter(
                account__type=Account.Type.ASSET,
                type=JournalEntryItem.JournalEntryType.DEBIT,
                amortization__isnull=True,
                journal_entry__transaction__amortization__isnull=True,
            )
            .exclude(account__special_type=Account.SpecialType.PREPAID_EXPENSES)
            .select_related("journal_entry__transaction", "account")
        )
        return render_to_string(
            table_template, {"journal_entry_items": unattached_journal_entries}
        )

    def get_amortization_form_html(self, journal_entry_item=None):
        form = AmortizationForm()
        if journal_entry_item:
            form.initial["accrued_journal_entry_item"] = journal_entry_item
        form_template = "api/entry_forms/amortization-form.html"
        return render_to_string(form_template, {"form": form})

    def get_depreciation_form_html(self, journal_entry_item=None):
        form = DepreciationForm()
        if journal_entry_item:
            form.initial["accrued_journal_entry_item"] = journal_entry_item
        form_template = "api/entry_forms/depreciation-form.html"
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


class DepreciationFormView(AmortizationTableMixin, LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, journal_entry_item_id):
        journal_entry_item = get_object_or_404(
            JournalEntryItem, pk=journal_entry_item_id
        )
        depreciation_form_html = self.get_depreciation_form_html(journal_entry_item)
        return HttpResponse(depreciation_form_html)


class AmortizationView(AmortizationTableMixin, LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, *args, **kwargs):
        return self.render_page(request)

    def post(self, request):
        form = AmortizationForm(request.POST)

        if form.is_valid():
            form.save()
            return self.render_page(request)

        print(form.errors)


class DepreciationView(AmortizationTableMixin, LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def post(self, request):
        form = DepreciationForm(request.POST)

        if form.is_valid():
            form.save()
            return self.render_page(request)

        print(form.errors)
