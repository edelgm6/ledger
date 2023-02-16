from django.db.models import Sum
from api.models import JournalEntryItem

def get_account_balances(start_date, end_date):
    income_statement_accounts = JournalEntryItem.objects.filter(account__type__in=['income','expense'],journal_entry__date__gte=start_date,journal_entry__date__lte=end_date).values('account__name','account__type','type').annotate(total=Sum('amount'))
    balance_sheet_accounts = JournalEntryItem.objects.filter(account__type__in=['asset','liability','equity']).values('account__name','account__type','type').annotate(total=Sum('amount'))

    # TODO: Turn all of this logic into something that is done in a helper function
    account_balances = {}
    account_groups = [income_statement_accounts,balance_sheet_accounts]
    for account_group in account_groups:
        for entry in account_group:
            account_name = entry['account__name']
            account_type = entry['account__type']
            journal_entry_type = entry['type']
            if not account_balances.get(account_name):
                account_balances[account_name] = {
                    'type': account_type,
                    'debits': 0,
                    'credits': 0
                }
            if journal_entry_type == 'credit':
                account_balances[account_name]['credits'] = entry['total']
            elif journal_entry_type == 'debit':
                account_balances[account_name]['debits'] = entry['total']

    account_balance_list = []
    for key, value in account_balances.items():
        balance = 0
        if value['type'] in ('asset','expense'):
            balance = value['debits'] - value['credits']
        else:
            balance = value['credits'] - value['debits']

        account_balance_list.append({'account': key, 'balance': balance})

    return account_balance_list