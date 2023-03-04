from django.test import TestCase
from rest_framework.test import APIRequestFactory
from api.statement import BalanceSheet, IncomeStatement
from api.models import Account, JournalEntryItem, JournalEntry

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
            sub_type='credit_card'
        )
        groceries = Account.objects.create(
            name='5000-Groceries',
            type='expense',
            sub_type='purchase'
        )
        insurance = Account.objects.create(
            name='6000-Insurance',
            type='expense',
            sub_type='purchase'
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-01')
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

        journal_entry = JournalEntry.objects.create(date='2023-01-28')
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
        journal_entry = JournalEntry.objects.create(date='2023-01-28')
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

    def test_create_balance_sheet(self):
        balance_sheet = BalanceSheet('2023-01-31')

    def test_creates_balances(self):
        balance_sheet = BalanceSheet('2023-01-31')
        chase_balance = [balance['balance'] for balance in balance_sheet.balances if balance['account'] == '1200-Chase'][0]
        print(balance_sheet.balances)
        self.assertEqual(len(balance_sheet.balances), 4)
        self.assertEqual(chase_balance, 300)

    def test_returns_cash_balance(self):
        balance_sheet = BalanceSheet('2023-01-31')
        total_cash = [summary['value'] for summary in balance_sheet.summaries if summary['name'] == 'Total Cash'][0]
        self.assertEqual(total_cash, 100)


class IncomeStatementTest(TestCase):

    def setUp(self):
        chase = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='credit_card'
        )
        groceries = Account.objects.create(
            name='5000-Groceries',
            type='expense',
            sub_type='purchase'
        )
        insurance = Account.objects.create(
            name='6000-Insurance',
            type='expense',
            sub_type='purchase'
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-01')
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

        journal_entry = JournalEntry.objects.create(date='2023-01-28')
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

    def test_create_income_statement(self):
        income_statement = IncomeStatement('2023-01-31','2023-01-01')

    def test_creates_balances(self):
        income_statement = IncomeStatement('2023-01-31','2023-01-01')
        net_income = [balance['balance'] for balance in income_statement.balances if balance['account'] == 'Net Income'][0]
        self.assertEqual(len(income_statement.balances), 3)
        self.assertEqual(net_income, -200)
