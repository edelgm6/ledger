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
    TransactionFilterResult,
    delete_transaction,
    filter_transactions,
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


class FilterEntryPointParityTest(TestCase):
    """The form and the service must build the same transactions queryset.

    They each constructed it by hand from the same eight arguments and had
    already drifted: the form omitted suggested_account from select_related, so
    whether a page issued an extra query per row depended on which entry point
    rendered it.
    """

    def setUp(self):
        self.account = AccountFactory(type=Account.Type.ASSET)
        self.suggested = AccountFactory(type=Account.Type.EXPENSE)
        for _ in range(3):
            TransactionFactory(
                account=self.account,
                suggested_account=self.suggested,
                is_closed=False,
                type=Transaction.TransactionType.PURCHASE,
                amount=Decimal("-10.00"),
            )

    def _bound_form(self):
        from api.forms import TransactionFilterForm

        form = TransactionFilterForm(
            {
                "is_closed": False,
                "transaction_type": [Transaction.TransactionType.PURCHASE],
                "account": [],
                "related_account": [],
                "suggested_first": False,
            },
            prefix=None,
        )
        self.assertTrue(form.is_valid(), form.errors)
        return form

    def test_both_entry_points_return_the_same_rows(self):
        from_form = list(self._bound_form().get_transactions())
        from_service = filter_transactions(
            is_closed=False,
            transaction_types=[Transaction.TransactionType.PURCHASE],
        ).transactions

        self.assertEqual(
            [t.pk for t in from_form], [t.pk for t in from_service]
        )

    def test_form_path_also_prefetches_suggested_account(self):
        """Touching suggested_account must not trigger an extra query."""
        transactions = list(self._bound_form().get_transactions())
        self.assertEqual(len(transactions), 3)

        with self.assertNumQueries(0):
            for txn in transactions:
                _ = txn.account.name
                _ = txn.suggested_account.name
