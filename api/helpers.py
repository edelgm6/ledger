import datetime
from django.db.models import Sum, Case, When, Value, DecimalField
from api.models import JournalEntryItem

def is_last_day_of_month(date):
    last_day_of_month = (date.replace(day=1) + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)
    return date == last_day_of_month

def get_account_balances(start_date, end_date):
    INCOME_STATEMENT_ACCOUNT_TYPES = ['income','expense']
    BALANCE_SHEET_ACCOUNT_TYPES = ['asset','liability','equity']
    income_statement_aggregates = JournalEntryItem.objects.filter(
            account__type__in=INCOME_STATEMENT_ACCOUNT_TYPES,
            journal_entry__date__gte=start_date,
            journal_entry__date__lte=end_date
            ).values('account__name','account__type').annotate(
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
            )
    balance_sheet_aggregates = JournalEntryItem.objects.filter(
        account__type__in=BALANCE_SHEET_ACCOUNT_TYPES,
        journal_entry__date__lte=end_date
        ).values('account__name','account__type').annotate(
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
        )

    account_balance_list = []
    aggregate_groups = [income_statement_aggregates,balance_sheet_aggregates]
    for group in aggregate_groups:
        for account_summary in group:
            account_type = account_summary['account__type']
            debits = account_summary['debit_total']
            credits = account_summary['credit_total']

            if account_type in ['asset','expense']:
                balance = debits - credits
            else:
                balance = credits - debits

            account_balance_list.append({'account': account_summary['account__name'], 'balance': balance, 'type': account_type})

    sorted_list = sorted(account_balance_list, key=lambda k: k['account'])
    return sorted_list