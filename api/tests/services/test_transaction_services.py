"""
Tests for transaction service layer.

These tests verify business logic and database operations in
transaction_services.py, ensuring atomicity and correctness.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from api.models import Account, Transaction
from api.services.transaction_services import (
    LinkResult,
    TransactionFilterResult,
    TransactionResult,
    apply_autotags_to_transactions,
    create_transaction,
    delete_transaction,
    filter_transactions,
    link_transactions,
    update_transaction,
)
from api.tests.testing_factories import AccountFactory, TransactionFactory


class FilterTransactionsTest(TestCase):
    """Tests for filter_transactions() function."""

    def setUp(self):
        self.account1 = AccountFactory(type=Account.Type.ASSET)
        self.account2 = AccountFactory(type=Account.Type.EXPENSE)

        # Create test transactions
        self.open_income = TransactionFactory(
            account=self.account1,
            is_closed=False,
            type=Transaction.TransactionType.INCOME,
            amount=Decimal("100.00"),
        )
        self.open_purchase = TransactionFactory(
            account=self.account1,
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
            amount=Decimal("-50.00"),
        )
        self.closed_transaction = TransactionFactory(
            account=self.account1,
            is_closed=True,
            type=Transaction.TransactionType.INCOME,
        )

    def test_filter_all_transactions(self):
        """Test filtering with no criteria returns all transactions."""
        result = filter_transactions()

        self.assertIsInstance(result, TransactionFilterResult)
        self.assertEqual(result.count, 3)
        self.assertEqual(len(result.transactions), 3)

    def test_filter_by_closed_status(self):
        """Test filtering by is_closed status."""
        result = filter_transactions(is_closed=False)

        self.assertEqual(result.count, 2)
        self.assertIn(self.open_income, result.transactions)
        self.assertIn(self.open_purchase, result.transactions)
        self.assertNotIn(self.closed_transaction, result.transactions)

    def test_filter_by_transaction_types(self):
        """Test filtering by transaction types."""
        result = filter_transactions(
            transaction_types=[Transaction.TransactionType.INCOME]
        )

        self.assertEqual(result.count, 2)
        self.assertIn(self.open_income, result.transactions)
        self.assertIn(self.closed_transaction, result.transactions)
        self.assertNotIn(self.open_purchase, result.transactions)

    def test_filter_by_account(self):
        """Test filtering by account."""
        other_account = AccountFactory()
        other_transaction = TransactionFactory(account=other_account)

        result = filter_transactions(accounts=[self.account1])

        self.assertEqual(result.count, 3)
        self.assertNotIn(other_transaction, result.transactions)

    def test_filter_by_date_range(self):
        """Test filtering by date range."""
        today = timezone.now().date()
        yesterday = today - timezone.timedelta(days=1)
        tomorrow = today + timezone.timedelta(days=1)

        # Create transaction with specific date
        old_transaction = TransactionFactory(
            account=self.account1,
            date=yesterday,
        )
        new_transaction = TransactionFactory(
            account=self.account1,
            date=tomorrow,
        )

        result = filter_transactions(
            date_from=today,
            date_to=today,
        )

        # Should only include transactions with today's date
        self.assertNotIn(old_transaction, result.transactions)
        self.assertNotIn(new_transaction, result.transactions)

    def test_filter_by_linked_status(self):
        """Test filtering by linked transaction status."""
        linked1 = TransactionFactory(account=self.account1)
        linked2 = TransactionFactory(account=self.account2)
        linked1.linked_transaction = linked2
        linked2.linked_transaction = linked1
        linked1.save()
        linked2.save()

        result = filter_transactions(has_linked_transaction=True)

        self.assertIn(linked1, result.transactions)
        self.assertIn(linked2, result.transactions)

        result = filter_transactions(has_linked_transaction=False)

        self.assertNotIn(linked1, result.transactions)
        self.assertNotIn(linked2, result.transactions)

    def test_filter_complex_criteria(self):
        """Test filtering with multiple criteria."""
        result = filter_transactions(
            is_closed=False,
            transaction_types=[Transaction.TransactionType.INCOME],
        )

        self.assertEqual(result.count, 1)
        self.assertEqual(result.transactions[0], self.open_income)


class CreateTransactionTest(TestCase):
    """Tests for create_transaction() function."""

    def setUp(self):
        self.account = AccountFactory(type=Account.Type.ASSET)
        self.suggested_account = AccountFactory(type=Account.Type.EXPENSE)

    def test_create_transaction_success(self):
        """Test creates transaction successfully."""
        result = create_transaction(
            date=timezone.now().date(),
            account=self.account,
            amount=Decimal("100.00"),
            description="Test transaction",
            suggested_account=self.suggested_account,
            transaction_type=Transaction.TransactionType.INCOME,
        )

        self.assertIsInstance(result, TransactionResult)
        self.assertTrue(result.success)
        self.assertIsNotNone(result.transaction)
        self.assertIsNone(result.error)
        self.assertEqual(result.transaction.amount, Decimal("100.00"))
        self.assertEqual(result.transaction.account, self.account)
        self.assertEqual(result.transaction.description, "Test transaction")

    def test_create_transaction_minimal_fields(self):
        """Test creates transaction with only required fields."""
        result = create_transaction(
            date=timezone.now().date(),
            account=self.account,
            amount=Decimal("50.00"),
            description="Minimal transaction",
            transaction_type=Transaction.TransactionType.PURCHASE,  # Required field
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.transaction)
        self.assertIsNone(result.transaction.suggested_account)

    def test_create_transaction_handles_error(self):
        """Test returns error result on exception."""
        # Mock Transaction.objects.create to raise an exception
        with patch.object(
            Transaction.objects, "create", side_effect=Exception("Database error")
        ):
            result = create_transaction(
                date=timezone.now().date(),
                account=self.account,
                amount=Decimal("100.00"),
                description="Test",
            )

        self.assertFalse(result.success)
        self.assertIsNone(result.transaction)
        self.assertIn("Database error", result.error)

    def test_create_transaction_atomic(self):
        """Test transaction creation is atomic."""
        initial_count = Transaction.objects.count()

        # Attempt to create with error
        with patch.object(
            Transaction.objects, "create", side_effect=Exception("Test error")
        ):
            result = create_transaction(
                date=timezone.now().date(),
                account=self.account,
                amount=Decimal("100.00"),
                description="Test",
            )

        # Verify nothing was created
        self.assertFalse(result.success)
        self.assertEqual(Transaction.objects.count(), initial_count)


class UpdateTransactionTest(TestCase):
    """Tests for update_transaction() function."""

    def setUp(self):
        self.account = AccountFactory()
        self.transaction = TransactionFactory(
            account=self.account,
            amount=Decimal("100.00"),
            description="Original description",
        )

    def test_update_transaction_amount(self):
        """Test updates transaction amount."""
        result = update_transaction(
            transaction_id=self.transaction.pk,
            amount=Decimal("150.00"),
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.transaction)
        self.assertEqual(result.transaction.amount, Decimal("150.00"))

        # Verify persisted
        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.amount, Decimal("150.00"))

    def test_update_transaction_description(self):
        """Test updates transaction description."""
        result = update_transaction(
            transaction_id=self.transaction.pk,
            description="Updated description",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.transaction.description, "Updated description")

    def test_update_transaction_multiple_fields(self):
        """Test updates multiple fields at once."""
        new_account = AccountFactory()
        result = update_transaction(
            transaction_id=self.transaction.pk,
            account=new_account,
            amount=Decimal("200.00"),
            description="New description",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.transaction.account, new_account)
        self.assertEqual(result.transaction.amount, Decimal("200.00"))
        self.assertEqual(result.transaction.description, "New description")

    def test_update_transaction_preserves_unchanged_fields(self):
        """Test unchanged fields remain unchanged."""
        original_description = self.transaction.description

        result = update_transaction(
            transaction_id=self.transaction.pk,
            amount=Decimal("200.00"),
        )

        self.assertTrue(result.success)
        self.assertEqual(result.transaction.description, original_description)

    def test_update_nonexistent_transaction(self):
        """Test returns error for nonexistent transaction."""
        result = update_transaction(
            transaction_id=99999,
            amount=Decimal("100.00"),
        )

        self.assertFalse(result.success)
        self.assertIsNone(result.transaction)
        self.assertIn("not found", result.error)

    def test_update_transaction_atomic(self):
        """Test update is atomic and rolls back on error."""
        original_amount = self.transaction.amount

        # Mock save to raise an exception
        with patch.object(Transaction, "save", side_effect=Exception("Save error")):
            result = update_transaction(
                transaction_id=self.transaction.pk,
                amount=Decimal("999.00"),
            )

        self.assertFalse(result.success)
        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.amount, original_amount)


class DeleteTransactionTest(TestCase):
    """Tests for delete_transaction() function."""

    def setUp(self):
        self.account = AccountFactory()
        self.transaction = TransactionFactory(account=self.account)

    def test_delete_transaction_success(self):
        """Test deletes transaction successfully."""
        transaction_id = self.transaction.pk

        result = delete_transaction(transaction_id)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.transaction)

        # Verify deleted
        self.assertFalse(Transaction.objects.filter(pk=transaction_id).exists())

    def test_delete_nonexistent_transaction(self):
        """Test returns error for nonexistent transaction."""
        result = delete_transaction(transaction_id=99999)

        self.assertFalse(result.success)
        self.assertIsNone(result.transaction)
        self.assertIn("not found", result.error)

    def test_delete_transaction_atomic(self):
        """Test deletion is atomic."""
        transaction_id = self.transaction.pk

        # Mock delete to raise an exception
        with patch.object(Transaction, "delete", side_effect=Exception("Delete error")):
            result = delete_transaction(transaction_id)

        # Verify deletion failed
        self.assertFalse(result.success)
        # Transaction should still exist
        self.assertTrue(Transaction.objects.filter(pk=transaction_id).exists())

    def test_delete_transaction_cascades(self):
        """Test deletion cascades to related journal entries."""
        from api.models import JournalEntry, JournalEntryItem

        # Create journal entry and items for transaction
        journal_entry = JournalEntry.objects.create(
            transaction=self.transaction,
            date=self.transaction.date,
        )
        JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            account=self.account,
            amount=Decimal("100.00"),
            type=JournalEntryItem.JournalEntryType.DEBIT,
        )

        transaction_id = self.transaction.pk
        journal_entry_id = journal_entry.pk

        result = delete_transaction(transaction_id)

        self.assertTrue(result.success)
        # Verify journal entry was cascade deleted
        self.assertFalse(JournalEntry.objects.filter(pk=journal_entry_id).exists())


class LinkTransactionsTest(TestCase):
    """Tests for link_transactions() function."""

    def setUp(self):
        self.account1 = AccountFactory()
        self.account2 = AccountFactory()
        self.transaction1 = TransactionFactory(account=self.account1)
        self.transaction2 = TransactionFactory(account=self.account2)

    def test_link_transactions_success(self):
        """Test links two transactions successfully."""
        result = link_transactions(
            transaction1_id=self.transaction1.pk,
            transaction2_id=self.transaction2.pk,
        )

        self.assertIsInstance(result, LinkResult)
        self.assertTrue(result.success)
        self.assertIsNotNone(result.transaction1)
        self.assertIsNotNone(result.transaction2)
        self.assertIsNone(result.error)

        # Verify bidirectional link
        self.transaction1.refresh_from_db()
        self.transaction2.refresh_from_db()
        self.assertEqual(self.transaction1.linked_transaction, self.transaction2)
        self.assertEqual(self.transaction2.linked_transaction, self.transaction1)

    def test_link_nonexistent_transaction(self):
        """Test returns error when transaction doesn't exist."""
        result = link_transactions(
            transaction1_id=self.transaction1.pk,
            transaction2_id=99999,
        )

        self.assertFalse(result.success)
        self.assertIsNone(result.transaction1)
        self.assertIsNone(result.transaction2)
        self.assertIn("not found", result.error)

    def test_link_transactions_atomic(self):
        """Test linking is atomic and rolls back on error."""
        # Mock bulk_update to raise an exception
        with patch.object(
            Transaction.objects, "bulk_update", side_effect=Exception("Link error")
        ):
            result = link_transactions(
                transaction1_id=self.transaction1.pk,
                transaction2_id=self.transaction2.pk,
            )

        # Verify link failed
        self.assertFalse(result.success)
        # Verify no links were created
        self.transaction1.refresh_from_db()
        self.transaction2.refresh_from_db()
        self.assertIsNone(self.transaction1.linked_transaction)
        self.assertIsNone(self.transaction2.linked_transaction)

    def test_link_multiple_pairs(self):
        """Test can link multiple pairs of transactions."""
        transaction3 = TransactionFactory(account=self.account1)
        transaction4 = TransactionFactory(account=self.account2)

        # Link 1 and 2
        result1 = link_transactions(self.transaction1.pk, self.transaction2.pk)
        self.assertTrue(result1.success)

        # Link 3 and 4 (separate pair)
        result2 = link_transactions(transaction3.pk, transaction4.pk)
        self.assertTrue(result2.success)

        # Verify both pairs are linked independently
        self.transaction1.refresh_from_db()
        self.transaction2.refresh_from_db()
        transaction3.refresh_from_db()
        transaction4.refresh_from_db()

        self.assertEqual(self.transaction1.linked_transaction, self.transaction2)
        self.assertEqual(transaction3.linked_transaction, transaction4)


class ApplyAutotagsToTransactionsTest(TestCase):
    """Tests for apply_autotags_to_transactions() function."""

    def setUp(self):
        self.account = AccountFactory()

    def test_apply_autotags_to_open_transactions(self):
        """Test applies autotags to open transactions by default."""
        open_transaction1 = TransactionFactory(account=self.account, is_closed=False)
        open_transaction2 = TransactionFactory(account=self.account, is_closed=False)
        closed_transaction = TransactionFactory(account=self.account, is_closed=True)

        # Mock the apply_autotags method
        with patch.object(Transaction, "apply_autotags") as mock_apply:
            count = apply_autotags_to_transactions()

        # Verify autotags were applied to open transactions
        mock_apply.assert_called_once()
        self.assertEqual(count, 2)

    def test_apply_autotags_to_specific_queryset(self):
        """Test applies autotags to specific queryset."""
        transaction1 = TransactionFactory(account=self.account)
        transaction2 = TransactionFactory(account=self.account)
        transaction3 = TransactionFactory(account=self.account)

        # Apply to specific subset
        queryset = Transaction.objects.filter(pk__in=[transaction1.pk, transaction2.pk])

        with patch.object(Transaction, "apply_autotags") as mock_apply:
            count = apply_autotags_to_transactions(transactions=queryset)

        # Verify applied to 2 transactions
        mock_apply.assert_called_once()
        self.assertEqual(count, 2)

    def test_apply_autotags_updates_fields(self):
        """Test verifies bulk_update is called with correct fields."""
        transaction = TransactionFactory(account=self.account, is_closed=False)

        with patch.object(Transaction, "apply_autotags"):
            with patch.object(Transaction.objects, "bulk_update") as mock_bulk_update:
                apply_autotags_to_transactions()

        # Verify bulk_update called with expected fields
        mock_bulk_update.assert_called_once()
        call_args = mock_bulk_update.call_args
        updated_fields = call_args[0][1]
        self.assertIn("suggested_account", updated_fields)
        self.assertIn("prefill", updated_fields)
        self.assertIn("type", updated_fields)
        self.assertIn("suggested_entity", updated_fields)

    def test_apply_autotags_returns_zero_for_empty_set(self):
        """Test returns 0 when no transactions match."""
        # No open transactions
        TransactionFactory(account=self.account, is_closed=True)

        count = apply_autotags_to_transactions()

        self.assertEqual(count, 0)
