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

    def get_summaries(self):

        summary_metrics = {}
        for balance in self.balances:
            sub_type = balance['sub_type']
            if not summaries.get(sub_type):
                summaries[sub_type] = 0

            summaries[sub_type] += balance['balance']

        summaries = [{'name': metric.key, 'value': metric.value} for metric in summary_metrics]

        return summaries

    def get_metrics(self):
        metrics = []
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
        total_retained_earnings, investment_gains_losses, net_retained_earnings = self.get_retained_earnings_values()
        self.balances += [
            {
                'account': '9000-Net Retained Earnings',
                'balance': net_retained_earnings,
                'type': Account.AccountType.EQUITY,
                'sub_type': Account.AccountSubType.RETAINED_EARNINGS
            },
            {
                'account': '9100-Investment Gains/Losses',
                'balance': investment_gains_losses,
                'type': Account.AccountType.EQUITY,
                'sub_type': Account.AccountSubType.RETAINED_EARNINGS
            }
        ]
        self.metrics = self.get_metrics()
        self.summaries = self.get_summaries()
        self.summaries.append({'name': 'Total Retained Earnings', 'value': total_retained_earnings})

    def get_retained_earnings_values(self):
        income_statement = IncomeStatement(end_date=self.end_date,start_date='1970-01-01')
        retained_earnings = income_statement.get_net_income()

        investment_gains_losses_account_name = Account.objects.get(sub_type=Account.AccountSubType.INVESTMENT_GAINS)
        investment_gains_losses = sum([balance['balance'] for balance in income_statement.balances if balance['account'] == investment_gains_losses_account_name])
        net_retained_earnings = retained_earnings - investment_gains_losses

        return retained_earnings, investment_gains_losses, net_retained_earnings

    def get_balance(self, account):
        balance = [balance['balance'] for balance in self.balances if balance['account'] == account.name][0]
        return balance

    def get_summaries(self):
        summaries = []
        summaries.append(
            {
                'name': 'Total Cash',
                'value': sum([balance['balance'] for balance in self.balances if balance['sub_type'] == Account.AccountSubType.CASH])
            }
        )

        return summaries

    def get_metrics(self):
        metrics = []
        return metrics