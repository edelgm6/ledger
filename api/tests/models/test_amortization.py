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
