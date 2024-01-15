import datetime
from django.test import TestCase
from django.core.exceptions import ValidationError
from decimal import Decimal
from api.models import Amortization, Account
from api.tests.testing_factories import AccountFactory, TransactionFactory

class AmortizationTests(TestCase):

    def setUp(self):
        self.suggested_account = AccountFactory.create()
        self.accrued_transaction = TransactionFactory.create()

    def test_create_amortization(self):
        # Test creating an Amortization instance
        amortization = Amortization.objects.create(
            accrued_transaction=self.accrued_transaction,
            amount=Decimal('1000.00'),
            periods=12,
            description="Amortization Test",
            suggested_account=self.suggested_account
        )
        self.assertEqual(amortization.accrued_transaction, self.accrued_transaction)
        self.assertEqual(amortization.amount, Decimal('1000.00'))
        self.assertEqual(amortization.periods, 12)
        self.assertEqual(amortization.description, "Amortization Test")
        self.assertEqual(amortization.suggested_account, self.suggested_account)
        self.assertFalse(amortization.is_closed)

    def test_amortize(self):
        prepaid_account = AccountFactory(
            special_type=Account.SpecialType.PREPAID_EXPENSES
        )
        amortization = Amortization.objects.create(
            accrued_transaction=self.accrued_transaction,
            amount=Decimal('1000.00'),
            periods=6,
            description="Amortization Test",
            suggested_account=self.suggested_account
        )
        amortization.amortize(datetime.date(2023,1,15))
        self.assertEqual(amortization.get_remaining_periods(), 5)
        self.assertEqual(amortization.get_remaining_balance(), Decimal('833.34'))
        self.assertEqual(amortization.get_related_transactions().count(), 1)
        self.assertEqual(amortization.get_related_transactions()[0].amount, Decimal('-166.66'))

        amortization.amortize(datetime.date(2023,1,16))
        amortization.amortize(datetime.date(2023,1,17))
        amortization.amortize(datetime.date(2023,1,18))
        amortization.amortize(datetime.date(2023,1,19))
        amortization.amortize(datetime.date(2023,1,20))
        self.assertEqual(amortization.get_remaining_periods(), 0)
        self.assertEqual(amortization.get_remaining_balance(), 0)
        self.assertEqual(amortization.get_related_transactions().count(), 6)
        self.assertEqual(amortization.get_related_transactions()[5].amount, Decimal('-166.70'))

        with self.assertRaises(ValidationError):
            amortization.amortize(datetime.date(2023,1,21))


    def test_get_remaining_balance(self):
        amortization = Amortization.objects.create(
            accrued_transaction=self.accrued_transaction,
            amount=Decimal('1000.00'),
            periods=12,
            description="Amortization Test",
            suggested_account=self.suggested_account
        )
        TransactionFactory(amortization=amortization, amount=-100)
        TransactionFactory(amortization=amortization, amount=-100)
        TransactionFactory(amortization=amortization, amount=-100)

        self.assertEqual(amortization.get_remaining_balance(), 700)

    def test_get_remaining_periods(self):
        amortization = Amortization.objects.create(
            accrued_transaction=self.accrued_transaction,
            amount=Decimal('1000.00'),
            periods=12,
            description="Amortization Test",
            suggested_account=self.suggested_account
        )
        TransactionFactory(amortization=amortization)
        TransactionFactory(amortization=amortization)
        TransactionFactory(amortization=amortization)

        self.assertEqual(amortization.get_remaining_periods(), 9)

    def test_get_related_transactions(self):
        amortization = Amortization.objects.create(
            accrued_transaction=self.accrued_transaction,
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
