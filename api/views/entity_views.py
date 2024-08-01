from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View
from django.shortcuts import get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Case, When, F, Value, DecimalField
from api.models import Account, JournalEntryItem, Entity
from api.forms import JournalEntryItemEntityForm

# TODO: Create a mixin to handle common logic
class EntityTagMixin:

    def get_entities_balances(self):
        entities_balances = JournalEntryItem.objects.exclude(entity__isnull=True).values('entity__id', 'entity__name').annotate(
            total_debits=Sum(
                Case(
                    When(type=JournalEntryItem.JournalEntryType.DEBIT, then=F('amount')),
                    default=Value(0),
                    output_field=DecimalField()
                )
            ),
            total_credits=Sum(
                Case(
                    When(type=JournalEntryItem.JournalEntryType.CREDIT, then=F('amount')),
                    default=Value(0),
                    output_field=DecimalField()
                )
            ),
            balance=F('total_credits') - F('total_debits')
        )
        return entities_balances

    def get_total_page_html(self, is_initial_load=False):
        # Need to create a new account sub type for payables
        relevant_account_types = [
            Account.SubType.ACCOUNTS_RECEIVABLE,
            Account.SubType.LONG_TERM_DEBT
        ]

        untagged_journal_entry_items = JournalEntryItem.objects.filter(
            entity__isnull=True,
            account__sub_type__in=relevant_account_types
        ).select_related('journal_entry__transaction')

        table_html = render_to_string('api/tables/payables-receivables-table.html', {'payables_receivables': untagged_journal_entry_items})
        try:
            initial_journal_entry_item = untagged_journal_entry_items[0]
        except KeyError:
            initial_journal_entry_item = None
        form_html = render_to_string(
            'api/entry_forms/entity-tag-form.html', 
            {
                'form': JournalEntryItemEntityForm(instance=initial_journal_entry_item),
                'journal_entry_item_id': initial_journal_entry_item.pk
            }
        )
        entity_balances_table_html = render_to_string(
            'api/tables/entity-balances-table.html',
            {
                'entities_balances': self.get_entities_balances()
            }
        )

        html = render_to_string(
            'api/views/payables-receivables.html', 
            {
                'table': table_html,
                'form': form_html,
                'is_initial_load': is_initial_load,
                'balances_table': entity_balances_table_html
            }
        )
        return html


class EntityHistoryTable(LoginRequiredMixin, EntityTagMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'    

    def get(self, request, entity_id):
        journal_entry_items = JournalEntryItem.objects.filter(entity__pk=entity_id).select_related('journal_entry__transaction').order_by('journal_entry__date')
        html = render_to_string(
            'api/tables/entity-history-table.html',
            {
                'journal_entry_items': journal_entry_items
            }
        )
        return HttpResponse(html)


class TagEntitiesForm(LoginRequiredMixin, EntityTagMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request, journal_entry_item_id):
        journal_entry_item = get_object_or_404(JournalEntryItem, pk=journal_entry_item_id)

        html = render_to_string(
            'api/entry_forms/entity-tag-form.html', 
            {
                'form': JournalEntryItemEntityForm(instance=journal_entry_item),
                'journal_entry_item_id': journal_entry_item.pk
            }
        )
        return HttpResponse(html)
    
    def post(self, request, journal_entry_item_id):
        journal_entry_item = get_object_or_404(JournalEntryItem, pk=journal_entry_item_id)

        form = JournalEntryItemEntityForm(request.POST, instance=journal_entry_item)
        if form.is_valid():
            form.save()

        html = self.get_total_page_html()
        return HttpResponse(html)

class TagEntitiesView(LoginRequiredMixin, EntityTagMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    def get(self, request):
        html = self.get_total_page_html(is_initial_load=True)
        self.get_entities_balances()

        return HttpResponse(html)