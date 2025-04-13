from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Case, DecimalField, F, Max, Sum, Value, When
from django.db.models.functions import Abs
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views import View

from api.forms import JournalEntryItemEntityForm
from api.models import Account, JournalEntryItem


# TODO: Create a mixin to handle common logic
class EntityTagMixin:

    def get_entities_balances(self):
        entities_balances = (
            JournalEntryItem.objects.filter(
                account__sub_type__in=[
                    Account.SubType.ACCOUNTS_RECEIVABLE,
                ]
            )
            .exclude(entity__isnull=True)
            .values("entity__id", "entity__name")
            .annotate(
                total_debits=Sum(
                    Case(
                        When(
                            type=JournalEntryItem.JournalEntryType.DEBIT,
                            then=F("amount"),
                        ),
                        default=Value(0),
                        output_field=DecimalField(),
                    )
                ),
                total_credits=Sum(
                    Case(
                        When(
                            type=JournalEntryItem.JournalEntryType.CREDIT,
                            then=F("amount"),
                        ),
                        default=Value(0),
                        output_field=DecimalField(),
                    )
                ),
                balance=F("total_credits") - F("total_debits"),
            )
            .annotate(
                abs_balance=Abs(F("balance")),  # Absolute value of the balance
                max_journalentry_date=Max(
                    "journal_entry__date"
                ),  # Maximum date for related JournalEntry
            )
            .order_by(
                "-abs_balance", "-max_journalentry_date"
            )  # Order by abs_balance and max date
        )

        return entities_balances

    def get_untagged_journal_entries_table_and_items(self):
        # Need to create a new account sub type for payables
        relevant_account_types = [
            Account.SubType.ACCOUNTS_RECEIVABLE,
        ]

        untagged_journal_entry_items = (
            JournalEntryItem.objects.filter(
                entity__isnull=True, account__sub_type__in=relevant_account_types
            )
            .select_related("journal_entry__transaction")
            .order_by("journal_entry__date")
        )

        html = (
            None
            if not untagged_journal_entry_items.exists()
            else render_to_string(
                "api/tables/payables-receivables-table.html",
                {"payables_receivables": untagged_journal_entry_items},
            )
        )

        return html, untagged_journal_entry_items

    def get_entities_balances_table_html(self, preselected_entity=None):
        if preselected_entity:
            entity_history_table_html = self.get_entity_history_table_html(
                entity_id=preselected_entity.id
            )
        else:
            entity_history_table_html = ""

        html = render_to_string(
            "api/tables/entity-balances-table.html",
            {
                "entities_balances": self.get_entities_balances(),
                "preselected_entity": preselected_entity,
                "entity_history_table": entity_history_table_html,
            },
        )

        return html

    def get_entity_history_table_html(self, entity_id):
        journal_entry_items = (
            JournalEntryItem.objects.filter(
                entity__pk=entity_id,
                account__sub_type__in=[
                    Account.SubType.ACCOUNTS_RECEIVABLE,
                ],
            )
            .select_related("journal_entry__transaction")
            .order_by("journal_entry__date")
        )
        if not journal_entry_items:
            return ""

        balance = 0
        for journal_entry_item in journal_entry_items:
            if journal_entry_item.type == JournalEntryItem.JournalEntryType.DEBIT:
                balance -= journal_entry_item.amount
            else:
                balance += journal_entry_item.amount

            journal_entry_item.balance = balance

        html = render_to_string(
            "api/tables/entity-history-table.html",
            {"journal_entry_items": journal_entry_items},
        )
        return html

    def get_total_page_html(
        self, is_initial_load=False, preloaded_entity=None, preselected_entity=None
    ):

        table_html, untagged_journal_entry_items = (
            self.get_untagged_journal_entries_table_and_items()
        )
        try:
            initial_journal_entry_item = untagged_journal_entry_items[0]
        except IndexError:
            initial_journal_entry_item = None
        initial_data = {"entity": preloaded_entity}
        entity_form = JournalEntryItemEntityForm(
            instance=initial_journal_entry_item, initial=initial_data
        )
        form_html = (
            None
            if initial_journal_entry_item is None
            else render_to_string(
                "api/entry_forms/entity-tag-form.html",
                {
                    "form": entity_form,
                    "journal_entry_item_id": initial_journal_entry_item.pk,
                },
            )
        )
        entity_balances_table_html = self.get_entities_balances_table_html(
            preselected_entity
        )

        html = render_to_string(
            "api/views/payables-receivables.html",
            {
                "table": table_html,
                "form": form_html,
                "is_initial_load": is_initial_load,
                "balances_table": entity_balances_table_html,
            },
        )
        return html


class UntagJournalEntryView(LoginRequiredMixin, EntityTagMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def post(self, request, journal_entry_item_id):
        journal_entry_item = get_object_or_404(
            JournalEntryItem, pk=journal_entry_item_id
        )
        entity = journal_entry_item.entity
        journal_entry_item.remove_entity()

        html = self.get_total_page_html(preselected_entity=entity)
        return HttpResponse(html)


class EntityHistoryTable(LoginRequiredMixin, EntityTagMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, entity_id):
        html = self.get_entity_history_table_html(entity_id)
        return HttpResponse(html)


class TagEntitiesForm(LoginRequiredMixin, EntityTagMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, journal_entry_item_id):
        journal_entry_item = get_object_or_404(
            JournalEntryItem, pk=journal_entry_item_id
        )

        html = render_to_string(
            "api/entry_forms/entity-tag-form.html",
            {
                "form": JournalEntryItemEntityForm(instance=journal_entry_item),
                "journal_entry_item_id": journal_entry_item.pk,
            },
        )
        return HttpResponse(html)

    def post(self, request, journal_entry_item_id):
        journal_entry_item = get_object_or_404(
            JournalEntryItem, pk=journal_entry_item_id
        )

        form = JournalEntryItemEntityForm(request.POST, instance=journal_entry_item)
        if form.is_valid():
            form.save()

        html = self.get_total_page_html(preloaded_entity=form.cleaned_data["entity"])
        return HttpResponse(html)


class TagEntitiesView(LoginRequiredMixin, EntityTagMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request):
        html = self.get_total_page_html(is_initial_load=True)
        self.get_entities_balances()

        return HttpResponse(html)
