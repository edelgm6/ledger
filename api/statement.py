from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
from collections import namedtuple
from django.db.models import Sum, Case, When, Value, DecimalField
from api.models import JournalEntryItem, Account


class Trend:

    def __init__(self, start_date, end_date):
        self.start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        self.end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

    def _get_month_ranges(self):
        current_date = self.start_date

        MonthRange = namedtuple('MonthRange', ['start', 'end'])
        ranges = []
        while current_date <= self.end_date:
            start_of_month = current_date
            end_of_month = current_date + relativedelta(day=31)
            end_of_month = min(end_of_month, self.end_date)  # Ensure end of month is not greater than end date
            month_range = MonthRange(start=start_of_month, end=end_of_month)
            ranges.append(month_range)
            current_date += relativedelta(months=1)

        return ranges

    def get_balances(self):

        ranges = self._get_month_ranges()

        balances = []
        for range in ranges:
            income_statement = IncomeStatement(end_date=range.end, start_date=range.start)
            balance_sheet = BalanceSheet(end_date=range.end)

            balance_sheet_start_date = range.start - timedelta(days=1)
            balance_sheet_start = BalanceSheet(end_date=balance_sheet_start_date)
            cash_flow_statement = CashFlowStatement(income_statement, balance_sheet_start, balance_sheet)

            balances += income_statement.get_balances()
            balances += balance_sheet.get_balances()
            balances += cash_flow_statement.get_balances()

        return balances


class Balance:

    def __init__(
        self,
        account: Account,
        amount: float,
        date: date,
        type: str = 'flow'
    ):
        self.account = account
        self.amount = amount
        self.date = date
        self.type = type


class Metric:

    def __init__(self, name, value, metric_type='total'):
        self.name = name
        self.value = value
        self.metric_type = metric_type


class Statement:

    def __init__(self, end_date):
        self.end_date = end_date

    # TODO: Is there a reason this is a staticmethod?
    @staticmethod
    def _get_balance_from_aggregates(
        aggregates,
        end_date=None,
        balance_type=None
    ):
        account_balance_list = []
        for aggregate in aggregates:
            account = aggregate['account']
            debits = aggregate['debit_total']
            credits = aggregate['credit_total']

            balance = Account.get_balance_from_debit_and_credit(
                account.type,
                debits=debits,
                credits=credits
            )
            account_balance_list.append(
                Balance(
                    account,
                    balance,
                    end_date,
                    balance_type
                )
            )

        sorted_list = sorted(account_balance_list, key=lambda k: k.account.name)
        return sorted_list

    def get_balances(self):
        if type(self) == IncomeStatement:
            ACCOUNT_TYPES = ['income', 'expense']
            aggregates = JournalEntryItem.objects.filter(
                account__type__in=ACCOUNT_TYPES,
                journal_entry__date__gte=self.start_date,
                journal_entry__date__lte=self.end_date
            )
        else:
            ACCOUNT_TYPES = ['asset', 'liability', 'equity']
            aggregates = JournalEntryItem.objects.filter(
                account__type__in=ACCOUNT_TYPES,
                journal_entry__date__lte=self.end_date
            )

        aggregates = list(aggregates.values(
            'account__name'
            ).annotate(
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
            ))
        # represented_accounts_names = [aggregate['account__name'] for aggregate in aggregates]
        # represented_accounts = set(Account.objects.filter(name__in=represented_accounts_names))

        # Convert to account objects and add accounts without any activity
        type_objects = [Account.Type[type_value.upper()] for type_value in ACCOUNT_TYPES]
        eligible_accounts = Account.objects.filter(type__in=type_objects)
        for account in eligible_accounts:
            account_in_aggregates = False
            for aggregate in aggregates:
                if account.name == aggregate['account__name']:
                    aggregate['account'] = account
                    account_in_aggregates = True
                    break
            if not account_in_aggregates:
                aggregates.append(
                    {
                        'account': account,
                        'account__name': account.name,
                        'debit_total': 0,
                        'credit_total': 0,
                    }
                )

        # unrepresented_accounts = eligible_accounts - represented_accounts
        # for account in unrepresented_accounts:
        #     new_balance = Balance(
        #         account=account.name,
        #         amount=0,
        #         account_type=account.type,
        #         account_sub_type=account.sub_type,
        #         date=self.end_date,
        #         type=balance_type)
        #     balances.append(new_balance)


        # TODO: Set this further up
        balance_type = 'flow'
        if type(self) == BalanceSheet:
            balance_type = 'stock'

        balances = self._get_balance_from_aggregates(aggregates, self.end_date, balance_type)
        return balances

    def get_summaries(self):
        summary_metrics = {}
        for balance in self.balances:
            account_type = Account.Type(balance.account.type).label
            if not summary_metrics.get(account_type):
                summary_metrics[account_type] = 0

            sub_type = Account.SubType(balance.account.sub_type).label
            if not summary_metrics.get(sub_type):
                summary_metrics[sub_type] = 0
            summary_metrics[account_type] += balance.amount
            summary_metrics[sub_type] += balance.amount

        summaries = [Metric(key, value) for key, value in summary_metrics.items()]

        return summaries


class CashFlowStatement(Statement):

    def __init__(self, income_statement, start_balance_sheet, end_balance_sheet):

        self.income_statement = income_statement
        self.start_balance_sheet = start_balance_sheet
        self.end_balance_sheet = end_balance_sheet
        self.balance_sheet_deltas = self.get_balance_sheet_account_deltas()
        self.net_income_less_gains_and_losses = self.income_statement.net_income - self.income_statement.investment_gains

        # TODO: Can definitely combine finding the balances and getting the totals
        self.balances = []
        self.cash_from_operations_balances = self.get_cash_from_operations_balances()
        self.cash_from_financing_balances = self.get_cash_from_financing_balances()
        self.cash_from_investing_balances = self.get_cash_from_investing_balances()
        self.net_cash_flow = 0
        for balances_list in [self.cash_from_operations_balances, self.cash_from_financing_balances, self.cash_from_investing_balances]:
            self.balances += balances_list
            self.net_cash_flow += self.get_cash_flow(balances_list)

        self.summaries = [
            Metric('Starting Cash', self.get_cash_balance(self.start_balance_sheet)),
            Metric('Ending Cash', self.get_cash_balance(self.end_balance_sheet)),
            Metric('Cash Flow From Operations', self.get_cash_flow(self.cash_from_operations_balances)),
            Metric('Cash Flow From Investing', self.get_cash_flow(self.cash_from_investing_balances)),
            Metric('Cash Flow From Financing', self.get_cash_flow(self.cash_from_financing_balances)),
            Metric('Net Cash Flow', self.net_cash_flow)
        ]

        self.metrics = [
            Metric('Levered post-tax Free Cash Flow', self.get_levered_after_tax_cash_flow()),
            Metric('Levered post-tax post-retirement Free Cash Flow', self.get_levered_after_tax_after_retirement_cash_flow())
        ]

    @staticmethod
    def get_cash_balance(balance_sheet):
        cash = sum([summary.value for summary in balance_sheet.summaries if summary.name == 'Cash'])
        return cash

    @staticmethod
    def get_cash_flow(balances_list):
        cash_flow = sum([balance.amount for balance in balances_list])
        return cash_flow

    def get_balances(self):
        return self.balances

    def get_levered_after_tax_cash_flow(self):
        return self.net_income_less_gains_and_losses + sum([summary.value for summary in self.summaries if summary.name == 'Cash Flow From Financing'])

    def get_levered_after_tax_after_retirement_cash_flow(self):
        levered_after_tax_cash_flow = self.get_levered_after_tax_cash_flow()
        cash_from_investing_balances = self.get_cash_from_investing_balances()
        retirement_cash_flow = sum([balance.amount for balance in cash_from_investing_balances if balance.account.sub_type == Account.SubType.SECURITIES_RETIREMENT])
        return levered_after_tax_cash_flow + retirement_cash_flow

    def get_balance_sheet_account_deltas(self):
        accounts = Account.objects.filter(type__in=[Account.Type.ASSET, Account.Type.LIABILITY, Account.Type.EQUITY])
        account_deltas = []
        for account in accounts:
            starting_balance = sum([balance.amount for balance in self.start_balance_sheet.balances if balance.account == account])
            ending_balance = sum([balance.amount for balance in self.end_balance_sheet.balances if balance.account == account])
            delta = ending_balance - starting_balance
            if account.type == Account.Type.ASSET:
                delta = delta * -1
            account_deltas.append(
                Balance(
                    account=account,
                    amount=delta,
                    date=self.end_balance_sheet.end_date
                )
            )

        return account_deltas

    def get_cash_from_operations_balances(self):
        realized_net_income_account = Account(
            name='Realized Net Income',
            type=Account.Type.EQUITY,
            sub_type=Account.SubType.RETAINED_EARNINGS
        )

        net_income_less_gains_and_losses = [
            Balance(
                account=realized_net_income_account,
                amount=self.net_income_less_gains_and_losses,
                date=self.end_balance_sheet.end_date
            )
        ]
        accounts_receivable_accounts = [balance for balance in self.balance_sheet_deltas if balance.account.sub_type == Account.SubType.ACCOUNTS_RECEIVABLE]
        short_term_debt_accounts = [balance for balance in self.balance_sheet_deltas if balance.account.sub_type == Account.SubType.SHORT_TERM_DEBT]
        taxes_payable_accounts = [balance for balance in self.balance_sheet_deltas if balance.account.sub_type == Account.SubType.TAXES_PAYABLE]
        return net_income_less_gains_and_losses + accounts_receivable_accounts + short_term_debt_accounts + taxes_payable_accounts

    def get_cash_from_financing_balances(self):
        long_term_debt = [balance for balance in self.balance_sheet_deltas if balance.account.sub_type == Account.SubType.LONG_TERM_DEBT]
        return long_term_debt

    def get_cash_from_investing_balances(self):
        start_date = self.income_statement.start_date
        end_date = self.income_statement.end_date
        account_sub_types = [Account.SubType.SECURITIES_RETIREMENT, Account.SubType.SECURITIES_UNRESTRICTED]
        exclude_journal_entries_with_sub_types = [Account.SubType.UNREALIZED_INVESTMENT_GAINS]

        # Use select_related to fetch related Account objects
        journal_entry_items = JournalEntryItem.objects.filter(
            journal_entry__date__gte=start_date,
            journal_entry__date__lte=end_date,
            account__sub_type__in=account_sub_types
        ).exclude(journal_entry__journal_entry_items__account__sub_type__in=exclude_journal_entries_with_sub_types).select_related('account')

        # Efficient processing of items
        account_adjustments = {}
        for item in journal_entry_items:
            account = item.account
            adjustment = item.amount if account.type in [Account.Type.LIABILITY, Account.Type.INCOME] else -item.amount
            adjustment *= -1 if item.type == JournalEntryItem.JournalEntryType.CREDIT else 1
            account_adjustments.setdefault(account, 0)
            account_adjustments[account] += adjustment

        # Constructing balances
        balances = [
            Balance(
                account=key,
                amount=value,
                date=self.end_balance_sheet.end_date
            )
                    for key, value in account_adjustments.items()]
        sorted_balances = sorted(balances, key=lambda k: k.account)

        return sorted_balances


class IncomeStatement(Statement):

    def __init__(self, end_date, start_date):
        super().__init__(end_date)
        self.start_date = start_date
        self.balances = self.get_balances()

        self.net_income = self.get_net_income()
        self.investment_gains = self.get_unrealized_gains_and_losses()

        realized_net_income_account = Account(
            name='Realized Net Income',
            type=Account.Type.EQUITY,
            sub_type=Account.SubType.RETAINED_EARNINGS
        )
        self.balances.append(
            Balance(
                account=realized_net_income_account,
                amount=self._get_non_investment_gains_net_income(),
                date=self.end_date
            )
        )
        unrealized_gain_loss_account = Account(
            name='Unrealized Gains/Losses',
            type=Account.Type.EQUITY,
            sub_type=Account.SubType.RETAINED_EARNINGS
        )
        self.balances.append(
            Balance(
                account=unrealized_gain_loss_account,
                amount=self.investment_gains,
                date=self.end_date
            )
        )
        self.summaries = self.get_summaries()

    def get_net_income(self):
        net_income = 0
        for balance in self.balances:
            if balance.account.type == Account.Type.INCOME:
                net_income += balance.amount
            elif balance.account.type == Account.Type.EXPENSE:
                net_income -= balance.amount

        return net_income

    def get_taxable_income(self):
        return sum([balance.amount for balance in self.balances if balance.account.type == Account.Type.INCOME and balance.account.sub_type not in [Account.SubType.UNREALIZED_INVESTMENT_GAINS, Account.SubType.OTHER_INCOME]])

    def get_unrealized_gains_and_losses(self):
        return sum([balance.amount for balance in self.balances if balance.account.sub_type == Account.SubType.UNREALIZED_INVESTMENT_GAINS])

    def _get_non_investment_gains_net_income(self):
        return self.net_income - self.investment_gains

    def get_tax_rate(self):
        taxable_income = sum([balance.amount for balance in self.balances if balance.account.sub_type in [Account.SubType.SALARY, Account.SubType.DIVIDENDS_AND_INTEREST]])
        taxes = sum([balance.amount for balance in self.balances if balance.account.sub_type == Account.SubType.TAX])
        if taxable_income == 0:
            return None
        return taxes / taxable_income

    def get_savings_rate(self):
        non_gains_net_income = self._get_non_investment_gains_net_income()
        non_gains_income = sum([balance.amount for balance in self.balances if balance.account.sub_type != Account.SubType.UNREALIZED_INVESTMENT_GAINS and balance.account.type == Account.Type.INCOME])
        if non_gains_income == 0:
            return None
        return non_gains_net_income / non_gains_income


class BalanceSheet(Statement):

    def __init__(self, end_date):
        super().__init__(end_date)
        self.balances = self.get_balances()
        investment_gains_losses, net_retained_earnings = self.get_retained_earnings_values()
        retained_earnings_account = Account(
            name='9000-Net Retained Earnings',
            type=Account.Type.EQUITY,
            sub_type=Account.SubType.RETAINED_EARNINGS
        )
        investment_gains_losses_account = Account(
            name='9100-Investment Gains/Losses',
            type=Account.Type.EQUITY,
            sub_type=Account.SubType.RETAINED_EARNINGS
        )
        self.balances += [
            Balance(
                account=retained_earnings_account,
                amount=net_retained_earnings,
                date=self.end_date
            ),
            Balance(
                account=investment_gains_losses_account,
                amount=investment_gains_losses,
                date=self.end_date
            )
        ]
        self.summaries = self.get_summaries()
        self.metrics = self.get_metrics()

    def get_retained_earnings_values(self):
        income_statement = IncomeStatement(end_date=self.end_date, start_date='1970-01-01')
        retained_earnings = income_statement.get_net_income()

        investment_gains_losses = sum([balance.amount for balance in income_statement.balances if balance.account.sub_type == Account.SubType.UNREALIZED_INVESTMENT_GAINS])
        net_retained_earnings = retained_earnings - investment_gains_losses

        return investment_gains_losses, net_retained_earnings

    def get_balance(self, account):
        try:
            balance = [balance.amount for balance in self.balances if balance.account == account][0]
        # Need this when there is no balance for a given account
        except IndexError:
            balance = 0
        return balance

    def get_metrics(self):
        metrics = [
            Metric('Cash % Assets', self.get_cash_percent_assets(), 'ratio'),
            Metric('Debt to Equity', self.get_debt_to_equity(), 'ratio'),
            Metric('Liquid Assets', self.get_liquid_assets()),
            Metric('Liquid Assets %', self.get_liquid_assets_percent(), 'ratio')
        ]
        return metrics

    def get_cash_percent_assets(self):
        cash = sum([summary.value for summary in self.summaries if summary.name == Account.SubType.CASH.label])
        assets = sum([summary.value for summary in self.summaries if summary.name == Account.Type.ASSET.label])
        if assets == 0:
            return None

        return cash / assets

    def get_debt_to_equity(self):
        liabilities = sum([summary.value for summary in self.summaries if summary.name == Account.Type.LIABILITY.label])
        equity = sum([summary.value for summary in self.summaries if summary.name == Account.Type.EQUITY.label])
        if equity == 0:
            return None

        return liabilities / equity

    def get_liquid_assets(self):
        cash = sum([summary.value for summary in self.summaries if summary.name == Account.SubType.CASH.label])
        brokerage = sum([summary.value for summary in self.summaries if summary.name == Account.SubType.SECURITIES_UNRESTRICTED.label])

        return cash + brokerage

    def get_liquid_assets_percent(self):
        liquid_assets = self.get_liquid_assets()
        assets = sum([summary.value for summary in self.summaries if summary.name == Account.Type.ASSET.label])

        if assets == 0:
            return None
        return liquid_assets / assets
