from django.db.models import Sum, Case, When, Value, DecimalField
from api.models import JournalEntryItem

def get_balance_sheet_account_balance(end_date, account):
    account_aggregate = JournalEntryItem.objects.filter(
        account=account,
        journal_entry__date__lte=end_date
    ).values('account').annotate(
        debit_total=Sum(
            Case(
                When(type='debit', then='amount'),
                output_field=DecimalField(),
                default=Value(0)
            )
        ),
        credit_total=Sum(
            Case(
                When(type='credit', then='amount'),
                output_field=DecimalField(),
                default=Value(0)
            )
        )
    )[0]

    balance = 0
    debits = account_aggregate['debit_total']
    credits = account_aggregate['credit_total']

    if account.type in ['asset','expense']:
        balance = debits - credits
    else:
        balance = credits - debits

    return balance

def get_account_balances(start_date, end_date, account_types=['income','expense','asset','liability','equity']):
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
        account_type = value['type']
        if account_type in account_types:
            if account_type in ('asset','expense'):
                balance = value['debits'] - value['credits']
            else:
                balance = value['credits'] - value['debits']

            account_balance_list.append({'account': key, 'balance': balance, 'type': value['type']})


    sorted_list = sorted(account_balance_list, key=lambda k: k['account'])
    return sorted_list