from django.test import TestCase
from django.db import IntegrityError
from api.tests.testing_factories import TransactionFactory, AccountFactory, ReconciliationFactory
from api.models import TaxCharge, Account, JournalEntry, JournalEntryItem
from datetime import date
from decimal import Decimal

class TaxChargeModelTests(TestCase):

    def setUp(self):
        self.property_tax_account = AccountFactory(special_type=Account.SpecialType.PROPERTY_TAXES, type=Account.Type.EXPENSE)
        self.property_tax_payable_account = AccountFactory(special_type=Account.SpecialType.PROPERTY_TAXES_PAYABLE, type=Account.Type.LIABILITY)
        AccountFactory(special_type=Account.SpecialType.STATE_TAXES, type=Account.Type.EXPENSE)
        AccountFactory(special_type=Account.SpecialType.STATE_TAXES_PAYABLE, type=Account.Type.LIABILITY)
        AccountFactory(special_type=Account.SpecialType.FEDERAL_TAXES, type=Account.Type.EXPENSE)
        AccountFactory(special_type=Account.SpecialType.FEDERAL_TAXES_PAYABLE, type=Account.Type.LIABILITY)

    def test_create_tax_charge(self):
        # Test creating a TaxCharge instance using the factory
        tax_charge = TaxCharge.objects.create(
            type=TaxCharge.Type.PROPERTY,
            date=date.today(),
            amount=Decimal('100.00')
        )
        self.assertEqual(tax_charge.type, TaxCharge.Type.PROPERTY)
        self.assertEqual(tax_charge.amount, Decimal('100.00'))
        self.assertEqual(str(tax_charge), str(date.today()) + ' ' + TaxCharge.Type.PROPERTY)

    def test_blocks_duplicate_tax_charges(self):
        TaxCharge.objects.create(
            type=TaxCharge.Type.PROPERTY,
            date=date.today(),
            amount=Decimal('100.00')
        )

        with self.assertRaises(IntegrityError):
            # Creating another TaxCharge with the same type and date
            duplicate_tax_charge = TaxCharge.objects.create(
                type=TaxCharge.Type.PROPERTY,
                date=date.today(),
                amount=Decimal('200.00')
            )

    def test_creates_tax_charge_side_effects(self):
        tax_charge = TaxCharge.objects.create(
            type=TaxCharge.Type.PROPERTY,
            date=date.today(),
            amount=Decimal('100.00')
        )

        self.assertTrue(tax_charge.transaction)
        self.assertEqual(tax_charge.transaction.amount, Decimal(100.00))
        self.assertEqual(self.property_tax_account.get_balance(end_date=date.today(), start_date = date.today()), Decimal(100.00))
        self.assertEqual(self.property_tax_payable_account.get_balance(end_date=date.today()), Decimal(100.00))

    def test_creates_tax_charge_side_effects_with_existing_transaction_and_jes(self):
        transaction = TransactionFactory(amount=10, account=self.property_tax_account)

        journal_entry = JournalEntry.objects.create(
            date=date.today(),
            transaction=transaction
        )

        debit = JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=transaction.amount,
            account=self.property_tax_account
        )
        credit = JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=transaction.amount,
            account=self.property_tax_payable_account
        )

        tax_charge = TaxCharge.objects.create(
            type=TaxCharge.Type.PROPERTY,
            date=date.today(),
            amount=Decimal('100.00'),
            transaction=transaction
        )

        self.assertTrue(tax_charge.transaction)
        self.assertEqual(tax_charge.transaction.amount, Decimal(100.00))
        self.assertEqual(self.property_tax_account.get_balance(end_date=date.today(), start_date = date.today()), Decimal(100.00))
        self.assertEqual(self.property_tax_payable_account.get_balance(end_date=date.today()), Decimal(100.00))

    def test_creates_tax_charge_side_effects_with_existing_reconciliation(self):
        transaction = TransactionFactory(amount=10, account=self.property_tax_account)
        reconciliation = ReconciliationFactory(
            account=self.property_tax_payable_account,
            date=date.today(),
            amount=5,
            transaction=None
        )

        tax_charge = TaxCharge.objects.create(
            type=TaxCharge.Type.PROPERTY,
            date=date.today(),
            amount=Decimal('100.00'),
            transaction=transaction
        )

        self.assertTrue(tax_charge.transaction)
        self.assertEqual(tax_charge.transaction.amount, Decimal(100.00))
        self.assertEqual(self.property_tax_account.get_balance(end_date=date.today(), start_date = date.today()), Decimal(100.00))
        self.assertEqual(self.property_tax_payable_account.get_balance(end_date=date.today()), Decimal(100.00))
        reconciliation.refresh_from_db()
        self.assertEqual(reconciliation.amount, Decimal(100.00))

    # Add more tests as needed, for example, to test other fields or behaviors
