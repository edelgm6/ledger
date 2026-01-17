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
        # Link the tax account to its payable account
        self.property_tax_account.tax_payable_account = self.property_tax_payable_account
        self.property_tax_account.save()

        self.state_tax_account = AccountFactory(special_type=Account.SpecialType.STATE_TAXES, type=Account.Type.EXPENSE)
        self.state_tax_payable_account = AccountFactory(special_type=Account.SpecialType.STATE_TAXES_PAYABLE, type=Account.Type.LIABILITY)
        self.federal_tax_account = AccountFactory(special_type=Account.SpecialType.FEDERAL_TAXES, type=Account.Type.EXPENSE)
        self.federal_tax_payable_account = AccountFactory(special_type=Account.SpecialType.FEDERAL_TAXES_PAYABLE, type=Account.Type.LIABILITY)

    def test_create_tax_charge(self):
        # Test creating a TaxCharge instance
        transaction = TransactionFactory(account=self.property_tax_account)
        tax_charge = TaxCharge.objects.create(
            account=self.property_tax_account,
            transaction=transaction,
            date=date.today(),
            amount=Decimal('100.00')
        )
        self.assertEqual(tax_charge.account, self.property_tax_account)
        self.assertEqual(tax_charge.amount, Decimal('100.00'))
        self.assertIn(str(date.today()), str(tax_charge))

    def test_blocks_duplicate_tax_charges(self):
        transaction1 = TransactionFactory(account=self.property_tax_account)
        TaxCharge.objects.create(
            account=self.property_tax_account,
            transaction=transaction1,
            date=date.today(),
            amount=Decimal('100.00')
        )

        with self.assertRaises(IntegrityError):
            # Creating another TaxCharge with the same account and date
            transaction2 = TransactionFactory(account=self.property_tax_account)
            TaxCharge.objects.create(
                account=self.property_tax_account,
                transaction=transaction2,
                date=date.today(),
                amount=Decimal('200.00')
            )

    def test_creates_tax_charge_side_effects(self):
        transaction = TransactionFactory(account=self.property_tax_account, amount=Decimal('50.00'))
        tax_charge = TaxCharge.objects.create(
            account=self.property_tax_account,
            transaction=transaction,
            date=date.today(),
            amount=Decimal('100.00')
        )

        self.assertTrue(tax_charge.transaction)
        # The transaction amount should be updated to match the tax charge amount
        transaction.refresh_from_db()
        self.assertEqual(transaction.amount, Decimal('100.00'))

    def test_creates_tax_charge_side_effects_with_existing_transaction_and_jes(self):
        transaction = TransactionFactory(amount=10, account=self.property_tax_account)

        journal_entry = JournalEntry.objects.create(
            date=date.today(),
            transaction=transaction
        )

        JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=transaction.amount,
            account=self.property_tax_account
        )
        JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=transaction.amount,
            account=self.property_tax_payable_account
        )

        tax_charge = TaxCharge.objects.create(
            account=self.property_tax_account,
            date=date.today(),
            amount=Decimal('100.00'),
            transaction=transaction
        )

        self.assertTrue(tax_charge.transaction)
        transaction.refresh_from_db()
        self.assertEqual(transaction.amount, Decimal('100.00'))

    def test_creates_tax_charge_side_effects_with_existing_reconciliation(self):
        transaction = TransactionFactory(amount=10, account=self.property_tax_account)
        reconciliation = ReconciliationFactory(
            account=self.property_tax_payable_account,
            date=date.today(),
            amount=5,
            transaction=None
        )

        tax_charge = TaxCharge.objects.create(
            account=self.property_tax_account,
            date=date.today(),
            amount=Decimal('100.00'),
            transaction=transaction
        )

        self.assertTrue(tax_charge.transaction)
        transaction.refresh_from_db()
        self.assertEqual(transaction.amount, Decimal('100.00'))
