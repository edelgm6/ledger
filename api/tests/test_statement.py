from django.test import TestCase
from rest_framework.test import APIRequestFactory
from api.statement import BalanceSheet, IncomeStatement, CashFlowStatement
from api.models import Account, JournalEntryItem, JournalEntry, Transaction

class BalanceSheetTest(TestCase):
    def setUp(self):
        gains_losses = Account.objects.create(
            name='8000-gains losses',
            type=Account.AccountType.EQUITY,
            sub_type=Account.AccountSubType.INVESTMENT_GAINS
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

        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=groceries
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-28',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=groceries,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )

        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=groceries
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-28',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=insurance,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )

        ally = Account.objects.create(
            name='1000-Ally',
            type='asset',
            sub_type='cash'
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=groceries
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-28',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=ally,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )
        income = Account.objects.create(
            name='8000-Income',
            type=Account.AccountType.INCOME,
            sub_type=Account.AccountSubType.SALARY
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=groceries
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-28',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=income,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )

    def test_create_balance_sheet(self):
        balance_sheet = BalanceSheet('2023-01-31')

    def test_creates_balances(self):
        balance_sheet = BalanceSheet('2023-01-31')
        chase_balance = [balance.amount for balance in balance_sheet.balances if balance.account == '1200-Chase'][0]
        self.assertEqual(len(balance_sheet.balances), 4)
        self.assertEqual(chase_balance, 400)

    def test_returns_cash_balance(self):
        balance_sheet = BalanceSheet('2023-01-31')
        total_cash = [summary.value for summary in balance_sheet.summaries if summary.name == 'Cash'][0]
        self.assertEqual(total_cash, 100)


class IncomeStatementTest(TestCase):

    def setUp(self):

        cash = Account.objects.create(
            name='900-Ally',
            type='asset',
            sub_type='cash'
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
            type=Account.AccountType.INCOME,
            sub_type=Account.AccountSubType.INVESTMENT_GAINS
        )
        income = Account.objects.create(
            name='8000-Income',
            type=Account.AccountType.INCOME,
            sub_type=Account.AccountSubType.SALARY
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=income
        )
        journal_entry = JournalEntry.objects.create(date='2023-01-28',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=groceries,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=income
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-28',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=insurance,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=income
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-28',transaction=transaction)

        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=income
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-28',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=vanguard,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )

        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=income
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-28',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=vanguard,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=income
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-28',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=income,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )

        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=income
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-28',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=income,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=cash,
            journal_entry=journal_entry
        )

    def test_create_income_statement(self):
        income_statement = IncomeStatement('2023-01-31','2023-01-01')

    def test_creates_balances(self):
        income_statement = IncomeStatement('2023-01-31','2023-01-01')
        net_income = [balance.amount for balance in income_statement.balances if balance.account == 'Net Income'][0]
        self.assertEqual(len(income_statement.balances), 5)
        self.assertEqual(net_income, 200)

    def test_net_income(self):
        income_statement = IncomeStatement('2023-01-31','2023-01-01')
        net_income = [balance.amount for balance in income_statement.balances if balance.account == 'Net Income'][0]
        self.assertEqual(len(income_statement.balances), 5)
        self.assertEqual(net_income, 200)
        self.assertEqual(income_statement.net_income, 200)

    def test_create_cash_flow_statement(self):
        income_statement = IncomeStatement('2023-01-31','2023-01-01')
        balance_sheet = BalanceSheet('2023-01-31')
        balance_sheet_start = BalanceSheet('2022-12-31')
        cash_flow_statement = CashFlowStatement(income_statement,balance_sheet_start,balance_sheet)
        print(cash_flow_statement.get_cash_balance(balance_sheet))
        print(cash_flow_statement.get_cash_balance(balance_sheet_start))

