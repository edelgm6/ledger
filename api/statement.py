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

    def get_summaries(self):
        summary_metrics = {}
        for balance in self.balances:
            account_type = Account.AccountType(balance['type']).label
            if not summary_metrics.get(account_type):
                summary_metrics[account_type] = 0

            sub_type = Account.AccountSubType(balance['sub_type']).label
            if not summary_metrics.get(sub_type):
                summary_metrics[sub_type] = 0
            summary_metrics[account_type] += balance['balance']
            summary_metrics[sub_type] += balance['balance']

        summaries = [{'name': key, 'value': value} for key, value in summary_metrics.items()]

        return summaries

class IncomeStatement(Statement):

    def __init__(self, end_date, start_date):
        super().__init__(end_date)
        self.start_date = start_date
        self.balances = self.get_balances()

        self.net_income = self.get_net_income
        self.balances.append({
            'account': 'Net Income',
            'balance': self.net_income(),
            'type': Account.AccountType.EQUITY,
            'sub_type': Account.AccountSubType.RETAINED_EARNINGS,
        })
        self.metrics = self.get_metrics()
        self.summaries = self.get_summaries()

    def get_metrics(self):
        metrics = [
            {
                'name': 'Non-Gains Net Income',
                'value': self.get_non_investment_gains_net_income
            }
        ]
        return metrics

    def get_net_income(self):
        net_income = 0
        for balance in self.balances:
            if balance['type'] == Account.AccountType.INCOME:
                net_income += balance['balance']
            elif balance['type'] == Account.AccountType.EXPENSE:
                net_income -= balance['balance']

        return net_income

    def get_non_investment_gains_net_income(self):
        investment_gains = sum([balance['balance'] for balance in self.balances if balance['type'] == Account.AccountSubType.INVESTMENT_GAINS])
        return self.net_income - investment_gains


class BalanceSheet(Statement):

    def __init__(self, end_date):
        super().__init__(end_date)
        self.balances = self.get_balances()
        investment_gains_losses, net_retained_earnings = self.get_retained_earnings_values()
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

    def get_retained_earnings_values(self):
        income_statement = IncomeStatement(end_date=self.end_date,start_date='1970-01-01')
        retained_earnings = income_statement.get_net_income()

        investment_gains_losses = sum([balance['balance'] for balance in income_statement.balances if balance['sub_type'] == Account.AccountSubType.INVESTMENT_GAINS])
        net_retained_earnings = retained_earnings - investment_gains_losses

        return investment_gains_losses, net_retained_earnings

    def get_balance(self, account):
        balance = [balance['balance'] for balance in self.balances if balance['account'] == account.name][0]
        return balance

    def get_metrics(self):
        metrics = []
        return metrics