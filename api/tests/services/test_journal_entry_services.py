from decimal import Decimal
from unittest.mock import Mock, patch

from django.db import transaction as db_transaction
from django.test import TestCase

from api.forms import TransactionFilterForm
from api.models import Account, Entity, JournalEntry, JournalEntryItem, Transaction
from api.services.journal_entry_services import (
    PostSaveContext,
    SaveResult,
    ValidationResult,
    _create_journal_entry_item,
    get_post_save_context,
    save_journal_entry,
    validate_journal_entry_balance,
)
from api.tests.testing_factories import (
    AccountFactory,
    JournalEntryFactory,
    JournalEntryItemFactory,
    TransactionFactory,
)


class ValidateJournalEntryBalanceTest(TestCase):
    """Tests for validate_journal_entry_balance() function."""

    def setUp(self):
        self.asset_account = AccountFactory(type=Account.Type.ASSET)
        self.expense_account = AccountFactory(type=Account.Type.EXPENSE)
        self.transaction = TransactionFactory(
            account=self.asset_account, amount=Decimal("100.00")
        )

    def test_validate_balanced_entry_with_correct_match(self):
        """Test validation passes when debits equal credits and transaction matches."""
        debits_data = [
            {
                "account": self.asset_account,
                "amount": Decimal("100.00"),
                "entity": None,
                "id": None,
            }
        ]
        credits_data = [
            {
                "account": self.expense_account,
                "amount": Decimal("100.00"),
                "entity": None,
                "id": None,
            }
        ]

        result = validate_journal_entry_balance(
            self.transaction, debits_data, credits_data
        )

        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.errors), 0)

    def test_validate_unbalanced_debits_credits(self):
        """Test validation fails when debits don't equal credits."""
        debits_data = [
            {
                "account": self.asset_account,
                "amount": Decimal("100.00"),
                "entity": None,
                "id": None,
            }
        ]
        credits_data = [
            {
                "account": self.expense_account,
                "amount": Decimal("75.00"),
                "entity": None,
                "id": None,
            }
        ]

        result = validate_journal_entry_balance(
            self.transaction, debits_data, credits_data
        )

        self.assertFalse(result.is_valid)
        self.assertGreaterEqual(len(result.errors), 1)
        self.assertIn("must balance", result.errors[0])

    def test_validate_missing_transaction_match(self):
        """Test validation fails when no item matches transaction account/amount."""
        debits_data = [
            {
                "account": self.expense_account,  # Wrong account
                "amount": Decimal("100.00"),
                "entity": None,
                "id": None,
            }
        ]
        credits_data = [
            {
                "account": self.expense_account,
                "amount": Decimal("100.00"),
                "entity": None,
                "id": None,
            }
        ]

        result = validate_journal_entry_balance(
            self.transaction, debits_data, credits_data
        )

        self.assertFalse(result.is_valid)
        self.assertIn("Must be one journal entry item", result.errors[0])

    def test_validate_multiple_transaction_matches(self):
        """Test validation fails when multiple items match transaction."""
        debits_data = [
            {
                "account": self.asset_account,
                "amount": Decimal("100.00"),
                "entity": None,
                "id": None,
            },
            {
                "account": self.asset_account,
                "amount": Decimal("100.00"),
                "entity": None,
                "id": None,
            },
        ]
        credits_data = [
            {
                "account": self.expense_account,
                "amount": Decimal("200.00"),
                "entity": None,
                "id": None,
            }
        ]

        result = validate_journal_entry_balance(
            self.transaction, debits_data, credits_data
        )

        self.assertFalse(result.is_valid)
        self.assertIn("Must be one journal entry item", result.errors[0])

    def test_validate_negative_transaction(self):
        """Test validation works correctly for negative (credit) transactions."""
        negative_transaction = TransactionFactory(
            account=self.asset_account, amount=Decimal("-50.00")
        )

        debits_data = [
            {
                "account": self.expense_account,
                "amount": Decimal("50.00"),
                "entity": None,
                "id": None,
            }
        ]
        credits_data = [
            {
                "account": self.asset_account,
                "amount": Decimal("50.00"),
                "entity": None,
                "id": None,
            }
        ]

        result = validate_journal_entry_balance(
            negative_transaction, debits_data, credits_data
        )

        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.errors), 0)

    def test_validate_with_empty_amounts(self):
        """Test validation handles items with no amount (empty forms)."""
        debits_data = [
            {
                "account": self.asset_account,
                "amount": Decimal("100.00"),
                "entity": None,
                "id": None,
            },
            {"account": None, "amount": None, "entity": None, "id": None},
        ]
        credits_data = [
            {
                "account": self.expense_account,
                "amount": Decimal("100.00"),
                "entity": None,
                "id": None,
            }
        ]

        result = validate_journal_entry_balance(
            self.transaction, debits_data, credits_data
        )

        # Should still pass - empty items are ignored
        self.assertTrue(result.is_valid)


class CreateJournalEntryItemTest(TestCase):
    """Tests for _create_journal_entry_item() helper function."""

    def setUp(self):
        self.journal_entry = JournalEntryFactory()
        self.account = AccountFactory()
        self.entity = Entity.objects.create(name="Test Entity")

    def test_create_item_returns_none_for_empty_amount(self):
        """Test returns None when amount is missing."""
        item_data = {"amount": None, "account": self.account, "entity": self.entity}

        result = _create_journal_entry_item(
            self.journal_entry, item_data, JournalEntryItem.JournalEntryType.DEBIT
        )

        self.assertIsNone(result)

    def test_create_item_creates_new(self):
        """Test creates new item when no ID provided."""
        item_data = {
            "amount": Decimal("100.00"),
            "account": self.account,
            "entity": self.entity,
            "id": None,
        }

        result = _create_journal_entry_item(
            self.journal_entry, item_data, JournalEntryItem.JournalEntryType.DEBIT
        )

        self.assertIsNotNone(result)
        self.assertIsNone(result.pk)  # Not saved yet
        self.assertEqual(result.amount, Decimal("100.00"))
        self.assertEqual(result.account, self.account)
        self.assertEqual(result.entity, self.entity)
        self.assertEqual(result.type, JournalEntryItem.JournalEntryType.DEBIT)

    def test_create_item_updates_existing(self):
        """Test updates existing item when ID provided."""
        existing_item = JournalEntryItemFactory(
            journal_entry=self.journal_entry,
            amount=Decimal("50.00"),
            type=JournalEntryItem.JournalEntryType.DEBIT,
        )

        new_account = AccountFactory()
        item_data = {
            "amount": Decimal("150.00"),
            "account": new_account,
            "entity": self.entity,
            "id": existing_item.pk,
        }

        result = _create_journal_entry_item(
            self.journal_entry, item_data, JournalEntryItem.JournalEntryType.DEBIT
        )

        self.assertEqual(result.pk, existing_item.pk)
        self.assertEqual(result.amount, Decimal("150.00"))
        self.assertEqual(result.account, new_account)


class SaveJournalEntryTest(TestCase):
    """Tests for save_journal_entry() function."""

    def setUp(self):
        self.asset_account = AccountFactory(type=Account.Type.ASSET)
        self.expense_account = AccountFactory(type=Account.Type.EXPENSE)
        self.entity = Entity.objects.create(name="Test Entity")
        self.transaction = TransactionFactory(
            account=self.asset_account, amount=Decimal("100.00"), is_closed=False
        )

    def test_save_creates_journal_entry(self):
        """Test JournalEntry is created if it doesn't exist."""
        debits_data = [
            {
                "account": self.asset_account,
                "amount": Decimal("100.00"),
                "entity": self.entity,
                "id": None,
            }
        ]
        credits_data = [
            {
                "account": self.expense_account,
                "amount": Decimal("100.00"),
                "entity": self.entity,
                "id": None,
            }
        ]

        result = save_journal_entry(
            self.transaction, debits_data, credits_data, paystub_id=None
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.journal_entry)
        self.assertEqual(result.journal_entry.transaction, self.transaction)
        self.assertIsNone(result.error)

    def test_save_creates_new_items(self):
        """Test new JournalEntryItems are bulk created."""
        debits_data = [
            {
                "account": self.asset_account,
                "amount": Decimal("100.00"),
                "entity": self.entity,
                "id": None,
            }
        ]
        credits_data = [
            {
                "account": self.expense_account,
                "amount": Decimal("100.00"),
                "entity": self.entity,
                "id": None,
            }
        ]

        result = save_journal_entry(
            self.transaction, debits_data, credits_data, paystub_id=None
        )

        self.assertTrue(result.success)
        items = JournalEntryItem.objects.filter(journal_entry=result.journal_entry)
        self.assertEqual(items.count(), 2)

        debit_item = items.filter(type=JournalEntryItem.JournalEntryType.DEBIT).first()
        self.assertEqual(debit_item.amount, Decimal("100.00"))
        self.assertEqual(debit_item.account, self.asset_account)

    def test_save_updates_existing_items(self):
        """Test existing JournalEntryItems are bulk updated."""
        # Create existing journal entry with items
        journal_entry = JournalEntryFactory(
            transaction=self.transaction, date=self.transaction.date
        )
        existing_debit = JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.asset_account,
            amount=Decimal("50.00"),
            type=JournalEntryItem.JournalEntryType.DEBIT,
        )
        existing_credit = JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.expense_account,
            amount=Decimal("50.00"),
            type=JournalEntryItem.JournalEntryType.CREDIT,
        )

        # Update with new amounts
        debits_data = [
            {
                "account": self.asset_account,
                "amount": Decimal("150.00"),
                "entity": self.entity,
                "id": existing_debit.pk,
            }
        ]
        credits_data = [
            {
                "account": self.expense_account,
                "amount": Decimal("150.00"),
                "entity": self.entity,
                "id": existing_credit.pk,
            }
        ]

        result = save_journal_entry(
            self.transaction, debits_data, credits_data, paystub_id=None
        )

        self.assertTrue(result.success)

        # Verify updates
        existing_debit.refresh_from_db()
        existing_credit.refresh_from_db()
        self.assertEqual(existing_debit.amount, Decimal("150.00"))
        self.assertEqual(existing_credit.amount, Decimal("150.00"))

    def test_save_closes_transaction(self):
        """Test transaction is closed after save."""
        debits_data = [
            {
                "account": self.asset_account,
                "amount": Decimal("100.00"),
                "entity": self.entity,
                "id": None,
            }
        ]
        credits_data = [
            {
                "account": self.expense_account,
                "amount": Decimal("100.00"),
                "entity": self.entity,
                "id": None,
            }
        ]

        result = save_journal_entry(
            self.transaction, debits_data, credits_data, paystub_id=None
        )

        self.assertTrue(result.success)
        self.transaction.refresh_from_db()
        self.assertTrue(self.transaction.is_closed)

    def test_save_skips_empty_items(self):
        """Test items with no amount are not created."""
        debits_data = [
            {
                "account": self.asset_account,
                "amount": Decimal("100.00"),
                "entity": self.entity,
                "id": None,
            },
            {"account": None, "amount": None, "entity": None, "id": None},
        ]
        credits_data = [
            {
                "account": self.expense_account,
                "amount": Decimal("100.00"),
                "entity": self.entity,
                "id": None,
            }
        ]

        result = save_journal_entry(
            self.transaction, debits_data, credits_data, paystub_id=None
        )

        self.assertTrue(result.success)
        items = JournalEntryItem.objects.filter(journal_entry=result.journal_entry)
        self.assertEqual(items.count(), 2)  # Only 2, not 3

    def test_save_atomic_rollback_on_error(self):
        """Test transaction rolls back on error - CRITICAL TEST."""
        # Store initial counts
        initial_je_count = JournalEntry.objects.count()
        initial_jei_count = JournalEntryItem.objects.count()

        # Create invalid data that will cause an error during save
        debits_data = [
            {
                "account": self.asset_account,
                "amount": Decimal("100.00"),
                "entity": self.entity,
                "id": None,
            }
        ]
        credits_data = [
            {
                "account": self.expense_account,
                "amount": Decimal("100.00"),
                "entity": self.entity,
                "id": None,
            }
        ]

        # Mock JournalEntry.objects.create to raise an exception
        with patch.object(JournalEntry.objects, "create", side_effect=Exception("Simulated error")):
            result = save_journal_entry(
                self.transaction, debits_data, credits_data, paystub_id=None
            )

        # Verify save failed
        self.assertFalse(result.success)
        self.assertIsNone(result.journal_entry)
        self.assertIn("Simulated error", result.error)

        # CRITICAL: Verify nothing was saved (rollback worked)
        self.assertEqual(JournalEntry.objects.count(), initial_je_count)
        self.assertEqual(JournalEntryItem.objects.count(), initial_jei_count)
        self.transaction.refresh_from_db()
        self.assertFalse(self.transaction.is_closed)

    def test_save_links_paystub(self):
        """Test paystub is linked to journal entry when provided."""
        # Create a mock paystub (we'll create it manually since there's no factory)
        from api.models import Paystub, S3File, Prefill

        prefill = Prefill.objects.create(name="Test Prefill")
        s3file = S3File.objects.create(
            prefill=prefill, url="https://example.com/test.pdf", user_filename="test.pdf"
        )
        paystub = Paystub.objects.create(
            document=s3file, page_id="page1", title="Test Paystub"
        )

        debits_data = [
            {
                "account": self.asset_account,
                "amount": Decimal("100.00"),
                "entity": self.entity,
                "id": None,
            }
        ]
        credits_data = [
            {
                "account": self.expense_account,
                "amount": Decimal("100.00"),
                "entity": self.entity,
                "id": None,
            }
        ]

        result = save_journal_entry(
            self.transaction, debits_data, credits_data, paystub_id=paystub.pk
        )

        self.assertTrue(result.success)
        paystub.refresh_from_db()
        self.assertEqual(paystub.journal_entry, result.journal_entry)

    def test_save_handles_invalid_paystub_gracefully(self):
        """Test invalid paystub ID doesn't break the save."""
        debits_data = [
            {
                "account": self.asset_account,
                "amount": Decimal("100.00"),
                "entity": self.entity,
                "id": None,
            }
        ]
        credits_data = [
            {
                "account": self.expense_account,
                "amount": Decimal("100.00"),
                "entity": self.entity,
                "id": None,
            }
        ]

        # Use a non-existent paystub ID
        result = save_journal_entry(
            self.transaction, debits_data, credits_data, paystub_id=99999
        )

        # Save should still succeed (paystub linking is optional)
        self.assertTrue(result.success)
        self.assertIsNotNone(result.journal_entry)


class GetPostSaveContextTest(TestCase):
    """Tests for get_post_save_context() function."""

    def setUp(self):
        self.account = AccountFactory()
        self.entity = Entity.objects.create(name="Test Entity")

        # Create test transactions
        self.transaction1 = TransactionFactory(
            account=self.account,
            is_closed=False,
            type=Transaction.TransactionType.INCOME,
        )
        self.transaction2 = TransactionFactory(
            account=self.account,
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )
        self.transaction3 = TransactionFactory(
            account=self.account, is_closed=True
        )  # Closed, should be filtered out

    def test_context_with_valid_filter(self):
        """Test uses filtered transactions when form valid."""
        # Create a valid filter form
        filter_form = Mock(spec=TransactionFilterForm)
        filter_form.is_valid.return_value = True
        filter_form.get_transactions.return_value = [self.transaction1, self.transaction2]

        # Create mock formsets (make them iterable)
        debit_formset = Mock()
        debit_formset.__iter__ = Mock(return_value=iter([]))
        credit_formset = Mock()
        credit_formset.__iter__ = Mock(return_value=iter([]))

        context = get_post_save_context(
            filter_form=filter_form,
            current_index=0,
            debit_formset=debit_formset,
            credit_formset=credit_formset,
        )

        self.assertEqual(len(context.transactions), 2)
        self.assertEqual(context.highlighted_transaction, self.transaction1)
        self.assertEqual(context.highlighted_index, 0)

    def test_context_with_invalid_filter(self):
        """Test falls back to default filter when form invalid."""
        # Create an invalid filter form
        filter_form = Mock(spec=TransactionFilterForm)
        filter_form.is_valid.return_value = False

        # Create mock formsets (make them iterable)
        debit_formset = Mock()
        debit_formset.__iter__ = Mock(return_value=iter([]))
        credit_formset = Mock()
        credit_formset.__iter__ = Mock(return_value=iter([]))

        context = get_post_save_context(
            filter_form=filter_form,
            current_index=0,
            debit_formset=debit_formset,
            credit_formset=credit_formset,
        )

        # Should use default filter (open transactions, INCOME or PURCHASE)
        self.assertEqual(len(context.transactions), 2)
        self.assertIn(self.transaction1, context.transactions)
        self.assertIn(self.transaction2, context.transactions)
        self.assertNotIn(self.transaction3, context.transactions)

    def test_context_handles_index_out_of_bounds(self):
        """Test resets to index 0 when current index invalid."""
        filter_form = Mock(spec=TransactionFilterForm)
        filter_form.is_valid.return_value = True
        filter_form.get_transactions.return_value = [self.transaction1, self.transaction2]

        # Create mock formsets (make them iterable)
        debit_formset = Mock()
        debit_formset.__iter__ = Mock(return_value=iter([]))
        credit_formset = Mock()
        credit_formset.__iter__ = Mock(return_value=iter([]))

        # Request index that doesn't exist
        context = get_post_save_context(
            filter_form=filter_form,
            current_index=10,
            debit_formset=debit_formset,
            credit_formset=credit_formset,
        )

        # Should reset to 0
        self.assertEqual(context.highlighted_index, 0)
        self.assertEqual(context.highlighted_transaction, self.transaction1)

    def test_context_extracts_created_entities(self):
        """Test collects entities created during form cleaning."""
        filter_form = Mock(spec=TransactionFilterForm)
        filter_form.is_valid.return_value = True
        filter_form.get_transactions.return_value = [self.transaction1]

        # Create mock formsets with created entities
        debit_form = Mock()
        debit_form.created_entity = self.entity
        debit_formset = Mock()
        debit_formset.__iter__ = Mock(return_value=iter([debit_form]))

        credit_form = Mock()
        delattr(credit_form, "created_entity")  # No created_entity attribute
        credit_formset = Mock()
        credit_formset.__iter__ = Mock(return_value=iter([credit_form]))

        context = get_post_save_context(
            filter_form=filter_form,
            current_index=0,
            debit_formset=debit_formset,
            credit_formset=credit_formset,
        )

        self.assertEqual(len(context.created_entities), 1)
        self.assertEqual(context.created_entities[0], self.entity)

    def test_context_with_no_transactions(self):
        """Test handles empty transaction list."""
        filter_form = Mock(spec=TransactionFilterForm)
        filter_form.is_valid.return_value = True
        filter_form.get_transactions.return_value = []

        # Create mock formsets (make them iterable)
        debit_formset = Mock()
        debit_formset.__iter__ = Mock(return_value=iter([]))
        credit_formset = Mock()
        credit_formset.__iter__ = Mock(return_value=iter([]))

        context = get_post_save_context(
            filter_form=filter_form,
            current_index=0,
            debit_formset=debit_formset,
            credit_formset=credit_formset,
        )

        self.assertEqual(len(context.transactions), 0)
        self.assertIsNone(context.highlighted_transaction)
        self.assertEqual(context.highlighted_index, 0)
        self.assertEqual(len(context.created_entities), 0)
