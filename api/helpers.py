from django.db.models import Sum
from api.models import JournalEntryItem

def get_account_balances(start_date, end_date):
    INCOME_STATEMENT_ACCOUNT_TYPES = ['income','expense']
    BALANCE_SHEET_ACCOUNT_TYPES = ['asset','liability','equity']
    income_statement_aggregates = JournalEntryItem.objects.filter(
            account__type__in=INCOME_STATEMENT_ACCOUNT_TYPES,
            journal_entry__date__gte=start_date,
            journal_entry__date__lte=end_date
            ).values(
                'account__name',
                'account__type',
                'type'
            ).annotate(total=Sum('amount'))
    balance_sheet_aggregates = JournalEntryItem.objects.filter(
        account__type__in=BALANCE_SHEET_ACCOUNT_TYPES,
        journal_entry__date__lte=end_date
        ).values(
            'account__name',
            'account__type',
            'type'
        ).annotate(total=Sum('amount'))

    account_summaries = {}
    aggregate_groups = [income_statement_aggregates,balance_sheet_aggregates]
    for aggregate_group in aggregate_groups:
        for entry in aggregate_group:
            account_name = entry['account__name']
            account_type = entry['account__type']
            journal_entry_type = entry['type']
            if not account_summaries.get(account_name):
                account_summaries[account_name] = {
                    'type': account_type,
                    'debits': 0,
                    'credits': 0
                }
            if journal_entry_type == 'credit':
                account_summaries[account_name]['credits'] = entry['total']
            elif journal_entry_type == 'debit':
                account_summaries[account_name]['debits'] = entry['total']

    account_balance_list = []
    for key, value in account_summaries.items():
        balance = 0
        if value['type'] in ('asset','expense'):
            balance = value['debits'] - value['credits']
        else:
            balance = value['credits'] - value['debits']

        account_balance_list.append({'account': key, 'balance': balance, 'type': value['type']})

    return account_balance_list