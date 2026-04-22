import datetime
from django.test import TestCase
from django.core.exceptions import ValidationError
from decimal import Decimal
from api.models import Amortization, Account, JournalEntry, JournalEntryItem
from api.tests.testing_factories import AccountFactory, TransactionFactory, JournalEntryFactory

class AmortizationTests(TestCase):

    def setUp(self):
        self.suggested_account = AccountFactory.create()
        self.prepaid_account = AccountFactory(
            special_type=Account.SpecialType.PREPAID_EXPENSES
        )
        # Create a JournalEntryItem for the accrued_journal_entry_item field
        transaction = TransactionFactory.create()
        journal_entry = JournalEntryFactory.create(transaction=transaction)
        self.accrued_journal_entry_item = JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal('1000.00'),
            account=self.prepaid_account,
        )

    def test_create_amortization(self):
        # Test creating an Amortization instance
        amortization = Amortization.objects.create(
            accrued_journal_entry_item=self.accrued_journal_entry_item,
            amount=Decimal('1000.00'),
            periods=12,
            description="Amortization Test",
            suggested_account=self.suggested_account
        )
        self.assertEqual(amortization.accrued_journal_entry_item, self.accrued_journal_entry_item)
        self.assertEqual(amortization.amount, Decimal('1000.00'))
        self.assertEqual(amortization.periods, 12)
        self.assertEqual(amortization.description, "Amortization Test")
        self.assertEqual(amortization.suggested_account, self.suggested_account)
        self.assertFalse(amortization.is_closed)

    def test_amortize(self):
        amortization = Amortization.objects.create(
            accrued_journal_entry_item=self.accrued_journal_entry_item,
            amount=Decimal('1000.00'),
            periods=6,
            description="Amortization Test",
            suggested_account=self.suggested_account
        )
        amortization.amortize(datetime.date(2023,1,15))
        remaining_balance, remaining_periods, _ = amortization.get_remaining_balance_and_periods_and_max_date()
        self.assertEqual(remaining_periods, 5)
        self.assertEqual(remaining_balance, Decimal('833.34'))
        self.assertEqual(amortization.get_related_transactions().count(), 1)
        self.assertEqual(amortization.get_related_transactions()[0].amount, Decimal('-166.66'))

        amortization.amortize(datetime.date(2023,1,16))
        amortization.amortize(datetime.date(2023,1,17))
        amortization.amortize(datetime.date(2023,1,18))
        amortization.amortize(datetime.date(2023,1,19))
        amortization.amortize(datetime.date(2023,1,20))
        remaining_balance, remaining_periods, _ = amortization.get_remaining_balance_and_periods_and_max_date()
        self.assertEqual(remaining_periods, 0)
        self.assertEqual(remaining_balance, 0)
        self.assertEqual(amortization.get_related_transactions().count(), 6)
        # Last payment includes any rounding remainder
        self.assertEqual(amortization.get_related_transactions()[5].amount, Decimal('-166.66'))

        with self.assertRaises(ValidationError):
            amortization.amortize(datetime.date(2023,1,21))


    def test_get_remaining_balance(self):
        amortization = Amortization.objects.create(
            accrued_journal_entry_item=self.accrued_journal_entry_item,
            amount=Decimal('1000.00'),
            periods=12,
            description="Amortization Test",
            suggested_account=self.suggested_account
        )
        TransactionFactory(amortization=amortization, amount=-100)
        TransactionFactory(amortization=amortization, amount=-100)
        TransactionFactory(amortization=amortization, amount=-100)

        remaining_balance, _, _ = amortization.get_remaining_balance_and_periods_and_max_date()
        self.assertEqual(remaining_balance, 700)

    def test_get_remaining_periods(self):
        amortization = Amortization.objects.create(
            accrued_journal_entry_item=self.accrued_journal_entry_item,
            amount=Decimal('1000.00'),
            periods=12,
            description="Amortization Test",
            suggested_account=self.suggested_account
        )
        TransactionFactory(amortization=amortization)
        TransactionFactory(amortization=amortization)
        TransactionFactory(amortization=amortization)

        _, remaining_periods, _ = amortization.get_remaining_balance_and_periods_and_max_date()
        self.assertEqual(remaining_periods, 9)

    def test_get_related_transactions(self):
        amortization = Amortization.objects.create(
            accrued_journal_entry_item=self.accrued_journal_entry_item,
            amount=Decimal('1000.00'),
            periods=12,
            description="Amortization Test",
            suggested_account=self.suggested_account
        )
        TransactionFactory(amortization=amortization)
        TransactionFactory(amortization=amortization)
        TransactionFactory(amortization=amortization)

        self.assertEqual(amortization.get_related_transactions().count(), 3)

    def test_round_down(self):
        NUMBER = 12.121234
        round_down = Amortization._round_down(n=NUMBER)
        self.assertEqual(round_down, 12.12)
        self.assertEqual(NUMBER, 12.121234)


class DepreciationTests(TestCase):

    def setUp(self):
        self.expense_account = AccountFactory.create(type=Account.Type.EXPENSE)
        self.asset_account = AccountFactory(
            type=Account.Type.ASSET, sub_type=Account.SubType.REAL_ESTATE
        )
        transaction = TransactionFactory.create()
        journal_entry = JournalEntryFactory.create(transaction=transaction)
        self.asset_jei = JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal('10000.00'),
            account=self.asset_account,
        )

    def test_create_depreciation(self):
        depreciation = Amortization.objects.create(
            accrued_journal_entry_item=self.asset_jei,
            amount=Decimal('10000.00'),
            salvage_value=Decimal('1000.00'),
            periods=60,
            description="Computer",
            suggested_account=self.expense_account,
        )
        self.assertEqual(depreciation.amount, Decimal('10000.00'))
        self.assertEqual(depreciation.salvage_value, Decimal('1000.00'))
        self.assertEqual(depreciation.periods, 60)
        self.assertTrue(depreciation.is_depreciation)
        self.assertEqual(depreciation.depreciable_base, Decimal('9000.00'))
        self.assertFalse(depreciation.is_closed)

    def test_depreciate_drains_to_salvage(self):
        depreciation = Amortization.objects.create(
            accrued_journal_entry_item=self.asset_jei,
            amount=Decimal('10000.00'),
            salvage_value=Decimal('1000.00'),
            periods=6,
            description="Computer",
            suggested_account=self.expense_account,
        )

        # depreciable_base = 9000; per period = 1500 exactly
        depreciation.amortize(datetime.date(2026, 1, 31))
        remaining_balance, remaining_periods, _ = (
            depreciation.get_remaining_balance_and_periods_and_max_date()
        )
        self.assertEqual(remaining_periods, 5)
        self.assertEqual(remaining_balance, Decimal('7500.00'))
        self.assertEqual(
            depreciation.get_related_transactions()[0].amount, Decimal('-1500.00')
        )
        # transaction credits the asset account (depreciation's anchor)
        self.assertEqual(
            depreciation.get_related_transactions()[0].account, self.asset_account
        )
        self.assertEqual(
            depreciation.get_related_transactions()[0].suggested_account,
            self.expense_account,
        )

        for day in range(2, 7):
            depreciation.amortize(datetime.date(2026, day, 28))

        remaining_balance, remaining_periods, _ = (
            depreciation.get_remaining_balance_and_periods_and_max_date()
        )
        self.assertEqual(remaining_periods, 0)
        self.assertEqual(remaining_balance, Decimal('0.00'))
        self.assertEqual(depreciation.get_related_transactions().count(), 6)
        self.assertTrue(depreciation.is_closed)

        with self.assertRaises(ValidationError):
            depreciation.amortize(datetime.date(2026, 7, 31))

    def test_depreciate_handles_rounding(self):
        # depreciable_base = 9000, periods = 7 → 1285.71 per period,
        # final period absorbs the rounding remainder (9000 - 6*1285.71 = 1285.74)
        depreciation = Amortization.objects.create(
            accrued_journal_entry_item=self.asset_jei,
            amount=Decimal('10000.00'),
            salvage_value=Decimal('1000.00'),
            periods=7,
            description="Equipment",
            suggested_account=self.expense_account,
        )

        for month in range(1, 7):
            depreciation.amortize(datetime.date(2026, month, 28))

        non_final_amounts = [
            t.amount for t in depreciation.get_related_transactions()
        ]
        self.assertTrue(all(a == Decimal('-1285.71') for a in non_final_amounts))

        depreciation.amortize(datetime.date(2026, 7, 31))
        final_amount = depreciation.get_related_transactions()[0].amount
        self.assertEqual(final_amount, Decimal('-1285.74'))

        remaining_balance, remaining_periods, _ = (
            depreciation.get_remaining_balance_and_periods_and_max_date()
        )
        self.assertEqual(remaining_periods, 0)
        self.assertEqual(remaining_balance, Decimal('0.00'))
        self.assertTrue(depreciation.is_closed)
