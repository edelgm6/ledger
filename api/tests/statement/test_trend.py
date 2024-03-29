from datetime import date
from django.test import TestCase
from api.statement import Trend
from api.models import Account, JournalEntryItem, JournalEntry, Transaction


class TrendTest(TestCase):
    def setUp(self):
        Account.objects.create(
            name='8000-gains losses',
            type=Account.Type.EQUITY,
            sub_type=Account.SubType.UNREALIZED_INVESTMENT_GAINS
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

        journal_entry = JournalEntry.objects.create(date='2023-01-28', transaction=transaction)
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
            account=groceries
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-28', transaction=transaction)
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

        journal_entry = JournalEntry.objects.create(date='2023-01-28', transaction=transaction)
        JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=ally,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )
        income = Account.objects.create(
            name='8000-Income',
            type=Account.Type.INCOME,
            sub_type=Account.SubType.SALARY
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=groceries
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-28', transaction=transaction)
        JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=income,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )

    def test_create_trend(self):
        trend = Trend('2023-01-01', '2023-06-30')
        self.assertTrue(trend.start_date)

    def test_month_ranges(self):
        trend = Trend('2023-01-01', '2023-06-30')
        ranges = trend._get_month_ranges()
        self.assertEqual(len(ranges), 6)
        self.assertEqual(ranges[0].start, date(2023, 1, 1))
        self.assertEqual(ranges[-1].start, date(2023, 6, 1))
        self.assertEqual(ranges[-1].end, date(2023, 6, 30))

    def test_balance_trends(self):
        trend = Trend('2023-01-01', '2023-06-30')
        balances = trend.get_balances()
        self.assertTrue(balances)
