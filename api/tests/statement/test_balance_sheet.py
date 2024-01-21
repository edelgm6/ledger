from decimal import Decimal
from django.test import TestCase
from api.statement import BalanceSheet, IncomeStatement
from api.models import Account, JournalEntryItem, JournalEntry, Transaction


class BalanceSheetTest(TestCase):

    def setUp(self):
        self.cash = Account.objects.create(
            name='900-Ally',
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH
        )
        self.tax = Account.objects.create(
            name='Taxes',
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.TAX
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=10,
            account=self.tax
        )
        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=10,
            account=self.tax,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=10,
            account=self.cash,
            journal_entry=journal_entry
        )
        chase = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='short_term_debt'
        )
        groceries = Account.objects.create(
            name='5000-Groceries',
            type='expense',
            sub_type='purchases'
        )
        insurance = Account.objects.create(
            name='6000-Insurance',
            type='expense',
            sub_type='purchases'
        )
        vanguard = Account.objects.create(
            name='7000-Vanguard',
            type=Account.Type.ASSET,
            sub_type=Account.SubType.SECURITIES_RETIREMENT
        )
        self.income = Account.objects.create(
            name='8000-Income',
            type=Account.Type.INCOME,
            sub_type=Account.SubType.SALARY
        )
        other_income = Account.objects.create(
            name='8100-Other Income',
            type=Account.Type.INCOME,
            sub_type=Account.SubType.OTHER_INCOME
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=150,
            account=other_income
        )
        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=150,
            account=self.cash,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=150,
            account=other_income,
            journal_entry=journal_entry
        )

        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=self.income
        )
        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=groceries,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=self.income
        )

        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=insurance,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=self.income
        )

        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )

        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=self.income
        )

        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=vanguard,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )

        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=self.income
        )

        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=vanguard,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=self.income
        )

        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=self.income,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )

        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=self.income
        )

        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=300,
            account=self.income,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=300,
            account=self.cash,
            journal_entry=journal_entry
        )
        mortgage = Account.objects.create(
            name='Mortgage',
            type=Account.Type.LIABILITY,
            sub_type=Account.SubType.LONG_TERM_DEBT
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=50,
            account=self.cash
        )
        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=50,
            account=mortgage,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=50,
            account=self.cash,
            journal_entry=journal_entry
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=-50,
            account=self.cash
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
            account=vanguard,
            journal_entry=journal_entry
        )
        unrealized_earnings = Account.objects.create(
            name='Unrealized Earnings',
            type=Account.Type.INCOME,
            sub_type=Account.SubType.UNREALIZED_INVESTMENT_GAINS
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=50,
            account=vanguard
        )
        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=50,
            account=unrealized_earnings,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=50,
            account=vanguard,
            journal_entry=journal_entry
        )

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
            balance.amount for balance in balance_sheet.balances if balance.account == '1200-Chase'
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
