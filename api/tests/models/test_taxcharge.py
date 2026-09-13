from django.test import TestCase
from django.db import IntegrityError
from api.tests.testing_factories import TransactionFactory, AccountFactory, ReconciliationFactory, EntityFactory
from api.models import TaxCharge, Account, JournalEntry, JournalEntryItem
from datetime import date
from decimal import Decimal

class TaxChargeModelTests(TestCase):

    def setUp(self):
        self.property_tax_account = AccountFactory(tax_kind=Account.TaxKind.PROPERTY, type=Account.Type.EXPENSE)
        self.property_tax_payable_account = AccountFactory(type=Account.Type.LIABILITY, sub_type=Account.SubType.TAXES_PAYABLE)
        # Link the tax account to its payable account
        self.property_tax_account.tax_payable_account = self.property_tax_payable_account
        self.property_tax_account.save()

        self.state_tax_account = AccountFactory(tax_kind=Account.TaxKind.STATE, type=Account.Type.EXPENSE)
        self.state_tax_payable_account = AccountFactory(type=Account.Type.LIABILITY, sub_type=Account.SubType.TAXES_PAYABLE)
        self.federal_tax_account = AccountFactory(tax_kind=Account.TaxKind.FEDERAL, type=Account.Type.EXPENSE)
        self.federal_tax_payable_account = AccountFactory(type=Account.Type.LIABILITY, sub_type=Account.SubType.TAXES_PAYABLE)

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

    def test_tags_journal_entry_items_with_account_default_entity(self):
        # Give each tax account a default entity
        expense_entity = EntityFactory()
        payable_entity = EntityFactory()
        self.property_tax_account.entity = expense_entity
        self.property_tax_account.save()
        self.property_tax_payable_account.entity = payable_entity
        self.property_tax_payable_account.save()

        transaction = TransactionFactory(account=self.property_tax_account)
        tax_charge = TaxCharge.objects.create(
            account=self.property_tax_account,
            transaction=transaction,
            date=date.today(),
            amount=Decimal('100.00')
        )

        debit = tax_charge.transaction.journal_entry.journal_entry_items.get(
            type=JournalEntryItem.JournalEntryType.DEBIT
        )
        credit = tax_charge.transaction.journal_entry.journal_entry_items.get(
            type=JournalEntryItem.JournalEntryType.CREDIT
        )
        self.assertEqual(debit.entity, expense_entity)
        self.assertEqual(credit.entity, payable_entity)

    def test_journal_entry_items_have_no_entity_when_account_has_no_default(self):
        transaction = TransactionFactory(account=self.property_tax_account)
        tax_charge = TaxCharge.objects.create(
            account=self.property_tax_account,
            transaction=transaction,
            date=date.today(),
            amount=Decimal('100.00')
        )

        for item in tax_charge.transaction.journal_entry.journal_entry_items.all():
            self.assertIsNone(item.entity)

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


class TaxChargeAccountSyncTests(TestCase):
    """Editing an existing charge must keep its transaction in step.

    TaxCharge stores its account (and date) twice: on itself and on the
    transaction it owns. save() used to sync only `amount` on the
    existing-transaction path, so editing the account on the edit form left the
    transaction pointing at the old account. Everything that reached through
    the transaction then stopped finding the charge.
    """

    def setUp(self):
        # tax_payable_account is one-to-one, so each tax account needs its own.
        self.state_payable = AccountFactory(
            type=Account.Type.LIABILITY, sub_type=Account.SubType.TAXES_PAYABLE
        )
        self.state_tax = AccountFactory(
            tax_kind=Account.TaxKind.STATE, type=Account.Type.EXPENSE
        )
        self.state_tax.tax_payable_account = self.state_payable
        self.state_tax.save()

        self.federal_payable = AccountFactory(
            type=Account.Type.LIABILITY, sub_type=Account.SubType.TAXES_PAYABLE
        )
        self.federal_tax = AccountFactory(
            tax_kind=Account.TaxKind.FEDERAL, type=Account.Type.EXPENSE
        )
        self.federal_tax.tax_payable_account = self.federal_payable
        self.federal_tax.save()

        self.charge = TaxCharge.objects.create(
            account=self.state_tax, date=date(2026, 3, 31), amount=Decimal("100.00")
        )

    def test_editing_account_syncs_the_transaction(self):
        self.charge.account = self.federal_tax
        self.charge.save()

        self.charge.refresh_from_db()
        self.charge.transaction.refresh_from_db()
        self.assertEqual(self.charge.transaction.account, self.federal_tax)

    def test_editing_date_syncs_transaction_and_journal_entry(self):
        new_date = date(2026, 4, 30)
        self.charge.date = new_date
        self.charge.save()

        self.charge.refresh_from_db()
        self.assertEqual(self.charge.transaction.date, new_date)
        self.assertEqual(
            self.charge.transaction.journal_entry.date,
            new_date,
            "a stale journal entry date strands the expense in the old month",
        )

    def test_edited_charge_is_still_found_by_its_own_filter(self):
        from api.services.tax_services import get_filtered_tax_charges

        self.charge.account = self.federal_tax
        self.charge.save()

        found = get_filtered_tax_charges(
            date_from=date(2026, 1, 1),
            date_to=date(2026, 12, 31),
            tax_type=self.federal_tax,
        )
        self.assertIn(self.charge, list(found))

    def test_bulk_factory_does_not_duplicate_an_edited_charge(self):
        """The taxes page calls create_bulk_tax_charges on every load. An edited
        charge used to look absent to it, so it re-created the row and hit the
        ("account", "date") unique constraint -- a hard 500 on every load."""
        from api.factories import TaxChargeFactory

        self.charge.account = self.federal_tax
        self.charge.save()

        # Must not raise IntegrityError.
        TaxChargeFactory.create_bulk_tax_charges(date=date(2026, 3, 31))

        self.assertEqual(
            TaxCharge.objects.filter(
                account=self.federal_tax, date=date(2026, 3, 31)
            ).count(),
            1,
        )
