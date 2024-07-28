from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views import View
from django.shortcuts import get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from api.models import Account, JournalEntryItem, Entity
from api.forms import JournalEntryItemEntityForm


class TagEntitiesView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'next'

    # Need to create a new account sub type for payables
    def get(self, request):
        relevant_account_types = [
            Account.SubType.ACCOUNTS_RECEIVABLE,
            Account.SubType.LONG_TERM_DEBT
        ]

        untagged_journal_entry_items = JournalEntryItem.objects.filter(
            entity__isnull=True,
            account__sub_type__in=relevant_account_types
        ).select_related('journal_entry__transaction')

        entity_balances = Entity.objects.all().prefetch_related('journal_entry_items')
        print(entity_balances)

        table_html = render_to_string('api/tables/payables-receivables-table.html', {'payables_receivables': untagged_journal_entry_items})
        form_html = render_to_string('api/entry_forms/entity-tag-form.html', {'form': JournalEntryItemEntityForm()})

        html = render_to_string(
            'api/views/payables-receivables.html', 
            {
                'table': table_html,
                'form': form_html
            }
        )

        return HttpResponse(html)