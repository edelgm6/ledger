from datetime import date
from decimal import Decimal
from django.test import TestCase
from api.statement import IncomeStatement, Trend
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
            type=Account.Type.LIABILITY,
            sub_type=Account.SubType.SHORT_TERM_DEBT
        )
        groceries = Account.objects.create(
            name='5000-Groceries',
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.OPERATING
        )
        insurance = Account.objects.create(
            name='6000-Insurance',
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.OPERATING
        )
        ally = Account.objects.create(
            name='1000-Ally',
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH
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

    def test_every_row_tagged_with_statement_origin(self):
        trend = Trend('2023-01-01', date(2023, 6, 30))
        valid = {'income_statement', 'balance_sheet', 'cash_flow'}
        self.assertTrue(
            all(b.statement in valid for b in trend.get_balances())
        )

    def test_depreciation_not_double_counted_in_income_rows(self):
        # A non-cash expense (depreciation) is booked in the income statement AND
        # re-emitted as a cash-flow operations add-back. The two must land as
        # separate, origin-tagged trend rows so summing income_statement rows
        # matches the standalone income statement (regression for 677 -> 1354).
        vehicle = Account.objects.create(
            name='1700-Vehicle',
            type=Account.Type.ASSET,
            sub_type=Account.SubType.VEHICLES,
        )
        deprec = Account.objects.create(
            name='7000-Vehicle Depreciation',
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.OPERATING,
            is_depreciation=True,
        )
        create_closed_transaction_with_journal_entry(
            date='2023-03-15',
            debit_account=deprec,
            credit_account=vehicle,
            amount=Decimal('677'),
            transaction_account=vehicle,
        )

        trend = Trend('2023-03-01', date(2023, 3, 31))
        balances = trend.get_balances()
        deprec_rows = [b for b in balances if b.account.name == deprec.name]
        is_rows = [b for b in deprec_rows if b.statement == 'income_statement']
        cf_rows = [b for b in deprec_rows if b.statement == 'cash_flow']

        # exactly one income-statement row (not two), and a separate cash-flow add-back
        self.assertEqual(len(is_rows), 1)
        self.assertEqual(is_rows[0].amount, Decimal('677'))
        self.assertEqual(len(cf_rows), 1)

        # reconstructing the income statement from tagged rows matches the engine
        income_stmt = IncomeStatement(
            end_date=date(2023, 3, 31), start_date=date(2023, 3, 1)
        )
        engine_expense = sum(
            b.amount for b in income_stmt.get_balances()
            if b.account.type == Account.Type.EXPENSE
        )
        tagged_expense = sum(
            b.amount for b in balances
            if b.statement == 'income_statement'
            and b.account.type == Account.Type.EXPENSE
        )
        self.assertEqual(tagged_expense, engine_expense)
