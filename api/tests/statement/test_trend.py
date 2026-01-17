from datetime import date
from decimal import Decimal
from django.test import TestCase
from api.statement import Trend
from api.models import Account
from api.tests.scenario_builders import (
    create_closed_transaction_with_journal_entry,
    create_multi_line_journal_entry,
)


class TrendTest(TestCase):
    def setUp(self):
        # Create required accounts
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
        ally = Account.objects.create(
            name='1000-Ally',
            type='asset',
            sub_type='cash'
        )
        income = Account.objects.create(
            name='8000-Income',
            type=Account.Type.INCOME,
            sub_type=Account.SubType.SALARY
        )

        txn_date = '2023-01-28'

        # Groceries purchase: Debit Groceries $100, Credit Chase $100
        create_closed_transaction_with_journal_entry(
            date=txn_date,
            debit_account=groceries,
            credit_account=chase,
            amount=Decimal('100'),
            transaction_account=groceries,
        )

        # Insurance purchase: Debit Insurance $100, Credit Chase $100
        create_closed_transaction_with_journal_entry(
            date=txn_date,
            debit_account=insurance,
            credit_account=chase,
            amount=Decimal('100'),
            transaction_account=groceries,
        )

        # Cash deposit: Debit Ally $100, Credit Chase $100
        create_closed_transaction_with_journal_entry(
            date=txn_date,
            debit_account=ally,
            credit_account=chase,
            amount=Decimal('100'),
            transaction_account=groceries,
        )

        # Multi-line income entry: Credit Income $100, Credit Chase $100
        create_multi_line_journal_entry(
            date=txn_date,
            entries=[
                {'account': income, 'type': 'credit', 'amount': Decimal('100')},
                {'account': chase, 'type': 'credit', 'amount': Decimal('100')},
            ],
            transaction_account=groceries,
            transaction_amount=Decimal('100'),
        )

    def test_create_trend(self):
        # Note: Trend class expects end_date as a date object (not string)
        trend = Trend('2023-01-01', date(2023, 6, 30))
        self.assertTrue(trend.start_date)

    def test_month_ranges(self):
        trend = Trend('2023-01-01', date(2023, 6, 30))
        ranges = trend._get_month_ranges()
        self.assertEqual(len(ranges), 6)
        self.assertEqual(ranges[0].start, date(2023, 1, 1))
        self.assertEqual(ranges[-1].start, date(2023, 6, 1))
        self.assertEqual(ranges[-1].end, date(2023, 6, 30))

    def test_balance_trends(self):
        trend = Trend('2023-01-01', date(2023, 6, 30))
        balances = trend.get_balances()
        self.assertTrue(balances)
