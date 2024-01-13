import datetime
from django.test import TestCase
from django.utils import timezone
from decimal import Decimal
from api.models import Transaction, Account
from api.tests.testing_factories import TransactionFactory, AccountFactory

class TransactionModelTest(TestCase):

    def setUp(self):
        # Create an account for use in transactions
        self.account = AccountFactory()

    def test_transaction_creation(self):
        """Test the creation of a Transaction instance."""
        transaction = TransactionFactory(account=self.account)
        self.assertIsNotNone(transaction.pk, "Should create a Transaction instance")

    def test_transaction_str_representation(self):
        """Test the string representation of the Transaction model."""
        transaction = TransactionFactory(account=self.account, description="Test Transaction")
        expected_representation = f"{transaction.date} {transaction.account.name} {transaction.description} ${transaction.amount}"
        self.assertEqual(str(transaction), expected_representation, "String representation should be correct")

    def test_close_method(self):
        """Test the close method of the Transaction model."""
        # Create a transaction instance
        transaction = TransactionFactory(is_closed=False, date_closed=None)

        # Ensure the transaction is initially not closed
        self.assertFalse(transaction.is_closed, "Transaction should initially be not closed")
        self.assertIsNone(transaction.date_closed, "date_closed should initially be None")

        # Close the transaction
        close_date = datetime.date(2022, 1, 1)  # Example date, change as needed
        transaction.close(close_date)

        # Reload the transaction from the database
        transaction.refresh_from_db()

        # Check that the transaction is now closed and the date_closed is set
        self.assertTrue(transaction.is_closed, "Transaction should be marked as closed")
        self.assertEqual(transaction.date_closed, close_date, "date_closed should be set to the provided date")

        # Test the default behavior (closing with today's date)
        today = datetime.date.today()
        transaction = TransactionFactory()  # Create another transaction
        transaction.close()  # Close without specifying a date

        # Reload from the database
        transaction.refresh_from_db()

        # Check that date_closed is set to today
        self.assertEqual(transaction.date_closed, today, "date_closed should be set to today's date by default")

    def test_create_link_method(self):
        """Test the create_link method of the Transaction model."""
        # Create two transaction instances
        transaction1 = TransactionFactory(account=self.account)
        transaction2 = TransactionFactory(account=self.account)

        # Ensure the initial state is as expected
        self.assertIsNone(transaction1.linked_transaction, "linked_transaction should initially be None")
        self.assertFalse(transaction2.is_closed, "Transaction should initially be not closed")

        # Use the create_link method to link transaction1 to transaction2
        transaction1.create_link(transaction2)

        # Reload the transactions from the database
        transaction1.refresh_from_db()
        transaction2.refresh_from_db()

        # Check that transaction1 is now linked to transaction2
        self.assertEqual(transaction1.linked_transaction, transaction2, "Transaction1 should be linked to Transaction2")
        self.assertEqual(transaction1.suggested_account, transaction2.account, "suggested_account should be set to transaction2's account")

        # Check that transaction2 is now closed
        self.assertTrue(transaction2.is_closed, "Transaction2 should be marked as closed")