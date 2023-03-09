from django.db.models import Sum, Case, When, Value, DecimalField
from api.models import JournalEntryItem, Account, JournalEntry, JournalEntryItem

class Balance:

    def __init__(self, account, amount, type, sub_type):
        self.account = account
        self.amount = amount
        self.type = type
        self.sub_type = sub_type

class Metric:

    def __init__(self, name, value):
        self.name = name
        self.value = value

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

            account_balance_list.append(Balance(aggregate['account__name'],balance,account_type,aggregate['account__sub_type']))

        sorted_list = sorted(account_balance_list, key=lambda k: k.account)
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
            account_type = Account.AccountType(balance.type).label
            if not summary_metrics.get(account_type):
                summary_metrics[account_type] = 0

            sub_type = Account.AccountSubType(balance.sub_type).label
            if not summary_metrics.get(sub_type):
                summary_metrics[sub_type] = 0
            summary_metrics[account_type] += balance.amount
            summary_metrics[sub_type] += balance.amount

        summaries = [Metric(key, value) for key, value in summary_metrics.items()]

        return summaries

    def get_summary_value(self, search):
        value = sum([summary.value for summary in self.summaries if summary.name in search])
        return value

class CashFlowStatement(Statement):

    def __init__(self, income_statement, start_balance_sheet, end_balance_sheet):
        self.income_statement = income_statement
        self.start_balance_sheet = start_balance_sheet
        self.end_balance_sheet = end_balance_sheet
        self.balance_sheet_deltas = self.get_balance_sheet_account_deltas()

        # TODO: Can definitely combine finding the balances and getting the totals
        self.balances = []
        cash_from_operations_balances = self.get_cash_from_operations_balances()
        cash_from_financing_balances = self.get_cash_from_financing_balances()
        cash_from_investing_balances = self.get_cash_from_investing_balances()
        for balances_list in [cash_from_operations_balances,cash_from_financing_balances,cash_from_investing_balances]:
            print(balances_list)
            self.balances += balances_list

        self.summaries = [
            Metric('Starting Cash', self.get_cash_balance(self.start_balance_sheet)),
            Metric('Ending Cash', self.get_cash_balance(self.end_balance_sheet)),
            Metric('Cash Flow From Operations', self.get_cash_from_operations()),
            Metric('Cash Flow From Investing', self.get_cash_from_investing()),
            Metric('Cash Flow From Financing', self.get_cash_from_financing()),
            Metric('Net Cash Flow', self.get_cash_from_operations() + self.get_cash_from_investing() + self.get_cash_from_financing())
        ]
        self.metrics = [
            Metric('Net Income', self.income_statement.net_income),
            Metric('Taxes Payable Change', self.get_taxes_payable_change()),
            Metric('Short Term Debt Change', self.get_short_term_debt_change()),
            Metric('Real Estate Change', self.get_real_estate_change()),
            Metric('Securities Change', self.get_securities_change()),
            Metric('Free cash flow', self.get_cash_from_operations() + self.get_cash_from_financing())
        ]

    @staticmethod
    def get_cash_balance(balance_sheet):
        cash = sum([summary.value for summary in balance_sheet.summaries if summary.name == 'Cash'])
        return cash

    def get_balance_sheet_account_deltas(self):
        accounts = Account.objects.filter(type__in=[Account.AccountType.ASSET,Account.AccountType.LIABILITY,Account.AccountType.EQUITY])
        account_deltas = []
        for account in accounts:
            starting_balance = sum([balance.amount for balance in self.start_balance_sheet.balances if balance.account == account.name])
            ending_balance = sum([balance.amount for balance in self.end_balance_sheet.balances if balance.account == account.name])
            account_deltas.append(Balance(account.name,ending_balance - starting_balance,account.type,account.sub_type))

        return account_deltas

    def get_cash_from_operations_balances(self):
        net_income_less_gains_and_losses = [
            Balance(
                'Net Income less Gains/Losses',
                self.income_statement.net_income - self.income_statement.investment_gains,
                Account.AccountType.EQUITY,Account.
                AccountSubType.RETAINED_EARNINGS
            )
        ]
        short_term_debt_accounts = [balance for balance in self.balance_sheet_deltas if balance.sub_type == Account.AccountSubType.SHORT_TERM_DEBT]
        taxes_payable_accounts = [balance for balance in self.balance_sheet_deltas if balance.sub_type == Account.AccountSubType.TAXES_PAYABLE]
        return net_income_less_gains_and_losses + short_term_debt_accounts + taxes_payable_accounts

    def get_cash_from_financing_balances(self):
        long_term_debt = [balance for balance in self.balance_sheet_deltas if balance.sub_type == Account.AccountSubType.LONG_TERM_DEBT]
        return long_term_debt

    def get_cash_from_investing_balances(self):
        start_date = self.income_statement.start_date
        end_date = self.income_statement.end_date
        account_sub_types = [Account.AccountSubType.SECURITIES_RETIREMENT,Account.AccountSubType.SECURITIES_UNRESTRICTED]
        exclude_journal_entries_with_sub_types = [Account.AccountSubType.INVESTMENT_GAINS]

        journal_entries = JournalEntry.objects.all()
        journal_entries = journal_entries.filter(date__gte=start_date, date__lte=end_date)
        journal_entries = journal_entries.exclude(journal_entry_items__account__sub_type__in=exclude_journal_entries_with_sub_types)

        journal_entry_items = JournalEntryItem.objects.filter(journal_entry__in=journal_entries)
        journal_entry_items = journal_entry_items.filter(account__sub_type__in=account_sub_types)

        account_adjustments = {}
        for item in journal_entry_items:
            if not account_adjustments.get(item.account):
                account_adjustments[item.account] = 0

            if item.account.type in [Account.AccountType.ASSET, Account.AccountType.EXPENSE]:
                if item.type == JournalEntryItem.JournalEntryType.DEBIT:
                    account_adjustments[item.account] += item.amount
                else:
                    account_adjustments[item.account] -= item.amount
            else:
                if item.type == JournalEntryItem.JournalEntryType.DEBIT:
                    account_adjustments[item.account] -= item.amount
                else:
                    account_adjustments[item.account] += item.amount

        balances = []
        for key, value in account_adjustments.items():
            balances.append(Balance(key.name,value,key.type,key.sub_type))
        sorted_balances = sorted(balances, key=lambda k: k.account)

        return sorted_balances

    def get_cash_from_operations(self):
        # Want to back out securities gains/losses from all metrics
        net_income = self.income_statement.get_non_investment_gains_net_income()
        taxes_payable_change = self.get_taxes_payable_change()
        short_term_debt_change = self.get_short_term_debt_change()

        return net_income + taxes_payable_change + short_term_debt_change

    def get_taxes_payable_change(self):
        taxes_payable_start = self.start_balance_sheet.get_summary_value([Account.AccountSubType.TAXES_PAYABLE.label])
        taxes_payable_end = self.end_balance_sheet.get_summary_value([Account.AccountSubType.TAXES_PAYABLE.label])
        return taxes_payable_end - taxes_payable_start

    def get_short_term_debt_change(self):
        short_term_debt_start = self.start_balance_sheet.get_summary_value([Account.AccountSubType.SHORT_TERM_DEBT.label])
        short_term_debt_end = self.end_balance_sheet.get_summary_value([Account.AccountSubType.SHORT_TERM_DEBT.label])
        return short_term_debt_end - short_term_debt_start

    def get_cash_from_investing(self):
        real_estate_change = self.get_real_estate_change()
        securities_change = self.get_securities_change()
        return real_estate_change + securities_change

    def get_securities_change(self):
        securities_start = self.start_balance_sheet.get_summary_value([Account.AccountSubType.SECURITIES_RETIREMENT.label, Account.AccountSubType.SECURITIES_UNRESTRICTED.label])
        securities_end = self.end_balance_sheet.get_summary_value([Account.AccountSubType.SECURITIES_RETIREMENT.label, Account.AccountSubType.SECURITIES_UNRESTRICTED.label])

        return securities_start - securities_end + self.income_statement.get_investment_gains_and_losses()

    def get_real_estate_change(self):
        real_estate_start = self.start_balance_sheet.get_summary_value([Account.AccountSubType.REAL_ESTATE.label])
        real_estate_end = self.end_balance_sheet.get_summary_value([Account.AccountSubType.REAL_ESTATE.label])
        return real_estate_start - real_estate_end

    def get_cash_from_financing(self):

        long_term_debt_start = self.start_balance_sheet.get_summary_value([Account.AccountSubType.LONG_TERM_DEBT.label])
        long_term_debt_end = self.end_balance_sheet.get_summary_value([Account.AccountSubType.LONG_TERM_DEBT.label])
        long_term_debt_change = long_term_debt_end - long_term_debt_start

        return long_term_debt_change

class IncomeStatement(Statement):

    def __init__(self, end_date, start_date):
        super().__init__(end_date)
        self.start_date = start_date
        self.balances = self.get_balances()

        self.net_income = self.get_net_income()
        self.investment_gains = self.get_investment_gains_and_losses()
        self.balances.append(Balance('Net Income', self.net_income, Account.AccountType.EQUITY, Account.AccountSubType.RETAINED_EARNINGS))
        self.metrics = self.get_metrics()
        self.summaries = self.get_summaries()

    def get_metrics(self):
        metrics = [
            Metric('Non-Gains Net Income', self.get_non_investment_gains_net_income()),
            Metric('Tax Rate', self.get_tax_rate()),
            Metric('Savings Rate', self.get_savings_rate())
        ]
        return metrics

    def get_net_income(self):
        net_income = 0
        for balance in self.balances:
            if balance.type == Account.AccountType.INCOME:
                net_income += balance.amount
            elif balance.type == Account.AccountType.EXPENSE:
                net_income -= balance.amount

        return net_income

    def get_investment_gains_and_losses(self):
        return sum([balance.amount for balance in self.balances if balance.sub_type == Account.AccountSubType.INVESTMENT_GAINS])

    def get_non_investment_gains_net_income(self):
        return self.net_income - self.investment_gains

    def get_tax_rate(self):
        taxable_income = sum([balance.amount for balance in self.balances if balance.sub_type in [Account.AccountSubType.SALARY, Account.AccountSubType.DIVIDENDS_AND_INTEREST]])
        taxes = sum([balance.amount for balance in self.balances if balance.sub_type == Account.AccountSubType.TAX])
        if taxable_income == 0:
            return None
        return taxes / taxable_income

    def get_savings_rate(self):
        non_gains_net_income = self.get_non_investment_gains_net_income()
        non_gains_income = sum([balance.amount for balance in self.balances if balance.sub_type != Account.AccountSubType.INVESTMENT_GAINS and balance.type == Account.AccountType.INCOME])
        if non_gains_income == 0:
            return None
        return non_gains_net_income / non_gains_income


class BalanceSheet(Statement):

    def __init__(self, end_date):
        super().__init__(end_date)
        self.balances = self.get_balances()
        investment_gains_losses, net_retained_earnings = self.get_retained_earnings_values()
        self.balances += [
            Balance('9000-Net Retained Earnings', net_retained_earnings, Account.AccountType.EQUITY, Account.AccountSubType.RETAINED_EARNINGS),
            Balance('9100-Investment Gains/Losses', investment_gains_losses, Account.AccountType.EQUITY, Account.AccountSubType.RETAINED_EARNINGS)
        ]
        self.summaries = self.get_summaries()
        self.metrics = self.get_metrics()

    def get_retained_earnings_values(self):
        income_statement = IncomeStatement(end_date=self.end_date,start_date='1970-01-01')
        retained_earnings = income_statement.get_net_income()

        investment_gains_losses = sum([balance.amount for balance in income_statement.balances if balance.sub_type == Account.AccountSubType.INVESTMENT_GAINS])
        net_retained_earnings = retained_earnings - investment_gains_losses

        return investment_gains_losses, net_retained_earnings

    def get_balance(self, account):
        balance = [balance.amount for balance in self.balances if balance.account == account.name][0]
        return balance

    def get_metrics(self):
        metrics = [
            Metric('Cash % Assets', self.get_cash_percent_assets()),
            Metric('Debt to Equity', self.get_debt_to_equity()),
            Metric('Liquid Assets', self.get_liquid_assets()),
            Metric('Liquid Assets %', self.get_liquid_assets_percent())
        ]
        return metrics

    def get_cash_percent_assets(self):
        cash = sum([summary.value for summary in self.summaries if summary.name == Account.AccountSubType.CASH.label])
        assets = sum([summary.value for summary in self.summaries if summary.name == Account.AccountType.ASSET.label])
        if assets == 0:
            return None

        return cash / assets

    def get_debt_to_equity(self):
        liabilities = sum([summary.value for summary in self.summaries if summary.name == Account.AccountType.LIABILITY.label])
        equity = sum([summary.value for summary in self.summaries if summary.name == Account.AccountType.EQUITY.label])
        if equity == 0:
            return None

        return liabilities / equity

    def get_liquid_assets(self):
        cash = sum([summary.value for summary in self.summaries if summary.name == Account.AccountSubType.CASH.label])
        brokerage = sum([summary.value for summary in self.summaries if summary.name == Account.AccountSubType.SECURITIES_UNRESTRICTED.label])

        return cash + brokerage

    def get_liquid_assets_percent(self):
        liquid_assets = self.get_liquid_assets()
        assets = sum([summary.value for summary in self.summaries if summary.name == Account.AccountType.ASSET.label])

        if assets == 0:
            return None
        return liquid_assets / assets