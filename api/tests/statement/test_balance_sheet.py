from decimal import Decimal
from django.test import TestCase
from api.statement import BalanceSheet, IncomeStatement
from api.models import Account, JournalEntryItem, JournalEntry, Transaction
from api.tests.scenario_builders import (
    create_closed_transaction_with_journal_entry,
    create_multi_line_journal_entry,
)


def create_standard_statement_scenario():
    """
    Create the standard set of accounts and transactions used across statement tests.

    Returns a dict with 'accounts' containing all created accounts.
    This helper reduces the ~250 lines of setUp to a single function call while
    maintaining the exact same data for backward compatibility.
    """
    accounts = {}
    txn_date = '2023-01-28'

    # Create accounts
    accounts['cash'] = Account.objects.create(
        name='900-Ally',
        type=Account.Type.ASSET,
        sub_type=Account.SubType.CASH
    )
    accounts['tax'] = Account.objects.create(
        name='Taxes',
        type=Account.Type.EXPENSE,
        sub_type=Account.SubType.TAX
    )
    accounts['chase'] = Account.objects.create(
        name='1200-Chase',
        type='liability',
        sub_type='short_term_debt'
    )
    accounts['groceries'] = Account.objects.create(
        name='5000-Groceries',
        type='expense',
        sub_type='purchases'
    )
    accounts['insurance'] = Account.objects.create(
        name='6000-Insurance',
        type='expense',
        sub_type='purchases'
    )
    accounts['vanguard'] = Account.objects.create(
        name='7000-Vanguard',
        type=Account.Type.ASSET,
        sub_type=Account.SubType.SECURITIES_RETIREMENT
    )
    accounts['income'] = Account.objects.create(
        name='8000-Income',
        type=Account.Type.INCOME,
        sub_type=Account.SubType.SALARY
    )
    accounts['other_income'] = Account.objects.create(
        name='8100-Other Income',
        type=Account.Type.INCOME,
        sub_type=Account.SubType.OTHER_INCOME
    )
    accounts['mortgage'] = Account.objects.create(
        name='Mortgage',
        type=Account.Type.LIABILITY,
        sub_type=Account.SubType.LONG_TERM_DEBT
    )
    accounts['unrealized_earnings'] = Account.objects.create(
        name='Unrealized Earnings',
        type=Account.Type.INCOME,
        sub_type=Account.SubType.UNREALIZED_INVESTMENT_GAINS
    )

    # Create transactions using scenario builders
    # Tax expense: Debit Taxes $10, Credit Cash $10
    create_closed_transaction_with_journal_entry(
        date=txn_date,
        debit_account=accounts['tax'],
        credit_account=accounts['cash'],
        amount=Decimal('10'),
        transaction_account=accounts['tax'],
    )

    # Other income: Debit Cash $150, Credit Other Income $150
    create_closed_transaction_with_journal_entry(
        date=txn_date,
        debit_account=accounts['cash'],
        credit_account=accounts['other_income'],
        amount=Decimal('150'),
        transaction_account=accounts['other_income'],
    )

    # Groceries: Debit Groceries $100, Credit Chase $100
    create_closed_transaction_with_journal_entry(
        date=txn_date,
        debit_account=accounts['groceries'],
        credit_account=accounts['chase'],
        amount=Decimal('100'),
        transaction_account=accounts['income'],
    )

    # Insurance: Debit Insurance $100, Credit Chase $100
    create_closed_transaction_with_journal_entry(
        date=txn_date,
        debit_account=accounts['insurance'],
        credit_account=accounts['chase'],
        amount=Decimal('100'),
        transaction_account=accounts['income'],
    )

    # Empty journal entry (transaction with no items)
    transaction = Transaction.objects.create(
        date=txn_date, amount=100, account=accounts['income'],
        is_closed=True, date_closed=txn_date
    )
    JournalEntry.objects.create(date=txn_date, transaction=transaction)

    # Two retirement contributions: Debit Chase $100, Credit Vanguard $100
    for _ in range(2):
        create_closed_transaction_with_journal_entry(
            date=txn_date,
            debit_account=accounts['chase'],
            credit_account=accounts['vanguard'],
            amount=Decimal('100'),
            transaction_account=accounts['income'],
        )

    # Multi-line entry: Credit Income $100, Credit Chase $100
    create_multi_line_journal_entry(
        date=txn_date,
        entries=[
            {'account': accounts['income'], 'type': 'credit', 'amount': Decimal('100')},
            {'account': accounts['chase'], 'type': 'credit', 'amount': Decimal('100')},
        ],
        transaction_account=accounts['income'],
        transaction_amount=Decimal('100'),
    )

    # Salary deposit: Debit Cash $300, Credit Income $300
    create_closed_transaction_with_journal_entry(
        date=txn_date,
        debit_account=accounts['cash'],
        credit_account=accounts['income'],
        amount=Decimal('300'),
        transaction_account=accounts['income'],
    )

    # Mortgage: Debit Cash $50, Credit Mortgage $50
    create_closed_transaction_with_journal_entry(
        date=txn_date,
        debit_account=accounts['cash'],
        credit_account=accounts['mortgage'],
        amount=Decimal('50'),
        transaction_account=accounts['cash'],
    )

    # Transfer: Debit Vanguard $50, Credit Cash $50
    create_closed_transaction_with_journal_entry(
        date=txn_date,
        debit_account=accounts['vanguard'],
        credit_account=accounts['cash'],
        amount=Decimal('50'),
        transaction_account=accounts['cash'],
    )

    # Unrealized gains: Debit Vanguard $50, Credit Unrealized $50
    create_closed_transaction_with_journal_entry(
        date=txn_date,
        debit_account=accounts['vanguard'],
        credit_account=accounts['unrealized_earnings'],
        amount=Decimal('50'),
        transaction_account=accounts['vanguard'],
    )

    return accounts


class BalanceSheetTest(TestCase):

    def setUp(self):
        accounts = create_standard_statement_scenario()
        self.cash = accounts['cash']
        self.income = accounts['income']

        START_DATE = '2023-01-01'
        END_DATE = '2023-01-31'
        self.start_balance_sheet = BalanceSheet(end_date=START_DATE)
        self.end_balance_sheet = BalanceSheet(end_date=END_DATE)
        self.income_statement = IncomeStatement(
            end_date=END_DATE,
            start_date=START_DATE
        )

    def test_create_balance_sheet(self):
        BalanceSheet('2023-01-31')

    def test_creates_balances(self):
        balance_sheet = BalanceSheet('2023-01-31')
        chase_balance = [
            balance.amount for balance in balance_sheet.balances if balance.account.name == '1200-Chase'
        ][0]
        self.assertEqual(len(balance_sheet.balances), 6)
        self.assertEqual(chase_balance, 100)

    def test_returns_cash_balance(self):
        balance_sheet = BalanceSheet('2023-01-31')
        total_cash = [summary.value for summary in balance_sheet.summaries if summary.name == 'Cash'][0]
        self.assertEqual(total_cash, 440)

    def test_get_retained_earnings_values(self):
        balance_sheet = BalanceSheet('2023-01-31')
        investment_gains_losses, net_retained_earnings = balance_sheet.get_retained_earnings_values()
        self.assertEqual(investment_gains_losses, 50)
        self.assertEqual(net_retained_earnings, 340)

    def test_get_balance(self):

        balance_sheet = BalanceSheet('2023-01-31')
        balance = balance_sheet.get_balance(self.cash)
        self.assertEqual(balance, 440)
        fake_account = Account.objects.create(
            name='Test',
            type=Account.Type.LIABILITY,
            sub_type=Account.SubType.LONG_TERM_DEBT
        )
        balance = balance_sheet.get_balance(fake_account)
        self.assertEqual(balance, 0)

    def test_get_cash_percent_assets(self):
        balance_sheet = BalanceSheet('2023-01-31')
        self.assertEqual(
            round(balance_sheet.get_cash_percent_assets(), 2), Decimal('1.29')
        )

    def test_get_debt_to_equity(self):
        balance_sheet = BalanceSheet('2023-01-31')
        self.assertEqual(round(balance_sheet.get_debt_to_equity(), 2), Decimal('.38'))
        # Debt == 150
        # Equity == 390

    def test_get_liquid_assets(self):
        balance_sheet = BalanceSheet('2023-01-31')
        self.assertEqual(balance_sheet.get_liquid_assets(), 440)

        four_01k = Account.objects.create(
            name='Test',
            type=Account.Type.ASSET,
            sub_type=Account.SubType.SECURITIES_UNRESTRICTED
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=50,
            account=four_01k
        )
        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=50,
            account=self.cash,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=50,
            account=four_01k,
            journal_entry=journal_entry
        )
        balance_sheet = BalanceSheet('2023-01-31')
        self.assertEqual(balance_sheet.get_liquid_assets(), 440)
