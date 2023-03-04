from django.db.models import Sum, Case, When, Value, DecimalField
from api.models import JournalEntryItem, Account

class Statement:

    def __init__(self, end_date):
        self.end_date = end_date

    @staticmethod
    def _get_balance_from_aggregates(aggregates):
        account_balance_list = []
        for aggregate in aggregates:
            account_type = aggregate['account__type']
            debits = aggregate['debit_total']
            credits = aggregate['credit_total']

            balance = Account.get_balance_from_debit_and_credit(account_type,debits=debits,credits=credits)

            account_balance_list.append(
                {
                    'account': aggregate['account__name'],
                    'balance': balance,
                    'type': account_type,
                    'sub_type': aggregate['account__sub_type']
                }
            )

        sorted_list = sorted(account_balance_list, key=lambda k: k['account'])
        return sorted_list

    def get_balances(self):
        if type(self) == IncomeStatement:
            ACCOUNT_TYPES = ['income','expense']
            aggregates = JournalEntryItem.objects.filter(
                account__type__in=ACCOUNT_TYPES,
                journal_entry__date__gte=self.start_date,
                journal_entry__date__lte=self.end_date
            )
        else:
            ACCOUNT_TYPES = ['asset','liability','equity']
            aggregates = JournalEntryItem.objects.filter(
                account__type__in=ACCOUNT_TYPES,
                journal_entry__date__lte=self.end_date
            )

        aggregates = aggregates.values(
            'account__name',
            'account__type',
            'account__sub_type').annotate(
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
        balances = self._get_balance_from_aggregates(aggregates)

        return balances

class IncomeStatement(Statement):

    def __init__(self, end_date, start_date):
        super().__init__(end_date)
        self.start_date = start_date
        self.balances = self.get_balances()
        self.balances.append({
            'account': 'Net Income',
            'balance': self.get_net_income(),
            'type': Account.AccountType.EQUITY,
            'sub_type': Account.AccountSubType.RETAINED_EARNINGS,
        })
        self.metrics = self.get_metrics()

    def get_metrics(self):
        metrics = []
        metrics.append(
            {
                'name': 'Net Income',
                'value': self.get_net_income()
            }
        )
        return metrics

    def get_net_income(self):
        net_income = 0
        for balance in self.balances:
            if balance['type'] == Account.AccountType.INCOME:
                net_income += balance['balance']
            elif balance['type'] == Account.AccountType.EXPENSE:
                net_income -= balance['balance']

        return net_income

class BalanceSheet(Statement):

    def __init__(self, end_date):
        super().__init__(end_date)
        self.balances = self.get_balances()
        self.metrics = self.get_metrics()

    def get_balance(self, account):
        balance = [balance['balance'] for balance in self.balances if balance['account'] == account.name][0]
        return balance

    def get_metrics(self):
        metrics = []
        metrics.append(
            {
                'name': 'Total Cash',
                'value': sum([balance['balance'] for balance in self.balances if balance['sub_type'] == Account.AccountSubType.CASH])
            }
        )
        return metrics