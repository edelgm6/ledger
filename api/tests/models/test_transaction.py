import datetime
from django.test import TestCase
from api.models import Transaction, TransactionQuerySet
from api.tests.testing_factories import TransactionFactory, AccountFactory, EntityFactory

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
        entity = EntityFactory()
        account2 = AccountFactory(entity=entity)
        transaction1 = TransactionFactory(account=self.account)
        transaction2 = TransactionFactory(account=account2)

        self.assertIsNone(transaction1.linked_transaction, "linked_transaction should initially be None")
        self.assertFalse(transaction2.is_closed, "Transaction should initially be not closed")

        transaction1.create_link(transaction2)

        transaction1.refresh_from_db()
        transaction2.refresh_from_db()

        self.assertEqual(transaction1.linked_transaction, transaction2)
        self.assertEqual(transaction1.suggested_account, account2)
        self.assertEqual(transaction1.suggested_entity, entity)
        self.assertTrue(transaction2.is_closed)

class TransactionQuerySetTest(TestCase):

    def setUp(self):
        self.account1 = AccountFactory()
        self.account2 = AccountFactory()
        # Create a set of transactions with varying attributes

        self.start_date = datetime.date(2022, 1, 1)
        self.middle_date = datetime.date(2022, 6, 11)
        self.end_date = datetime.date(2022, 12, 31)

        self.transaction1 = TransactionFactory(
            date=self.start_date,
            account=self.account1,
            is_closed=False,
            type=Transaction.TransactionType.INCOME
        )
        self.transaction2 = TransactionFactory(
            date=self.middle_date,
            account=self.account1,
            is_closed=True,
            type=Transaction.TransactionType.PURCHASE
        )
        self.transaction3 = TransactionFactory(
            date=self.end_date,
            account=self.account2,
            is_closed=False,
            type=Transaction.TransactionType.PAYMENT,
            linked_transaction=self.transaction1
        )

    def test_filter_for_table(self):
        # Test filtering by is_closed
        closed_transactions = Transaction.objects.filter_for_table(is_closed=True)
        self.assertIn(self.transaction2, closed_transactions)
        self.assertNotIn(self.transaction1, closed_transactions)
        self.assertNotIn(self.transaction3, closed_transactions)

        # Test filtering by has_linked_transaction
        with_linked_transactions = Transaction.objects.filter_for_table(has_linked_transaction=True)
        self.assertIn(self.transaction3, with_linked_transactions)
        self.assertNotIn(self.transaction1, with_linked_transactions)
        self.assertNotIn(self.transaction2, with_linked_transactions)

        # Test filtering by transaction_types
        income_transactions = Transaction.objects.filter_for_table(transaction_types=[Transaction.TransactionType.INCOME])
        self.assertIn(self.transaction1, income_transactions)
        self.assertNotIn(self.transaction2, income_transactions)
        self.assertNotIn(self.transaction3, income_transactions)

        # Test filtering by accounts
        account1_transactions = Transaction.objects.filter_for_table(accounts=[self.account1])
        self.assertIn(self.transaction1, account1_transactions)
        self.assertIn(self.transaction2, account1_transactions)
        self.assertNotIn(self.transaction3, account1_transactions)

        # Test filtering by date range
        date_range_transactions = Transaction.objects.filter_for_table(date_from=self.start_date, date_to=self.end_date)
        # Assuming the transactions are created today in setUp
        self.assertIn(self.transaction1, date_range_transactions)
        self.assertIn(self.transaction2, date_range_transactions)
        self.assertIn(self.transaction3, date_range_transactions)

    def test_filter_for_table_suggested_first(self):
        suggestion_account = AccountFactory()
        # An early-dated transaction WITHOUT a suggestion and a later-dated one WITH.
        untagged = TransactionFactory(
            date=self.start_date,
            account=self.account1,
            suggested_account=None,
        )
        tagged = TransactionFactory(
            date=self.end_date,
            account=self.account1,
            suggested_account=suggestion_account,
        )

        # Default ordering is purely by date/account/pk, so the older untagged
        # transaction comes before the newer tagged one.
        default_order = list(
            Transaction.objects.filter_for_table(accounts=[self.account1])
        )
        self.assertLess(
            default_order.index(untagged), default_order.index(tagged)
        )

        # With suggested_first, the tagged transaction floats above the untagged
        # one despite its later date.
        suggested_order = list(
            Transaction.objects.filter_for_table(
                accounts=[self.account1], suggested_first=True
            )
        )
        self.assertLess(
            suggested_order.index(tagged), suggested_order.index(untagged)
        )

    def test_filter_for_table_suggested_first_preserves_secondary_sort(self):
        suggestion_account = AccountFactory()
        earlier = TransactionFactory(
            date=self.start_date,
            account=self.account1,
            suggested_account=suggestion_account,
        )
        later = TransactionFactory(
            date=self.end_date,
            account=self.account1,
            suggested_account=suggestion_account,
        )

        # Within the suggested group, the existing date/account/pk order holds.
        ordered = list(
            Transaction.objects.filter_for_table(
                accounts=[self.account1], suggested_first=True
            )
        )
        self.assertLess(ordered.index(earlier), ordered.index(later))

class TransactionManagerTest(TestCase):
    def setUp(self):
        self.account1 = AccountFactory()
        self.account2 = AccountFactory()

        self.start_date = datetime.date(2022, 1, 1)
        self.middle_date = datetime.date(2022, 6, 11)
        self.end_date = datetime.date(2022, 12, 31)

        self.transaction1 = TransactionFactory(
            date=self.start_date,
            account=self.account1,
            is_closed=False,
            type=Transaction.TransactionType.INCOME
        )
        self.transaction2 = TransactionFactory(
            date=self.middle_date,
            account=self.account1,
            is_closed=True,
            type=Transaction.TransactionType.PURCHASE
        )
        self.transaction3 = TransactionFactory(
            date=self.end_date,
            account=self.account2,
            is_closed=False,
            type=Transaction.TransactionType.PAYMENT,
            linked_transaction=self.transaction1
        )

    def test_filter_for_table(self):
        # Test filtering by is_closed
        closed_transactions = Transaction.objects.filter_for_table(is_closed=True)
        self.assertIn(self.transaction2, closed_transactions)
        self.assertNotIn(self.transaction1, closed_transactions)
        self.assertNotIn(self.transaction3, closed_transactions)

        # Test filtering by has_linked_transaction
        with_linked_transactions = Transaction.objects.filter_for_table(has_linked_transaction=True)
        self.assertIn(self.transaction3, with_linked_transactions)
        self.assertNotIn(self.transaction1, with_linked_transactions)
        self.assertNotIn(self.transaction2, with_linked_transactions)

        # Test filtering by transaction_types
        income_transactions = Transaction.objects.filter_for_table(transaction_types=[Transaction.TransactionType.INCOME])
        self.assertIn(self.transaction1, income_transactions)
        self.assertNotIn(self.transaction2, income_transactions)
        self.assertNotIn(self.transaction3, income_transactions)

        # Test filtering by accounts
        account1_transactions = Transaction.objects.filter_for_table(accounts=[self.account1])
        self.assertIn(self.transaction1, account1_transactions)
        self.assertIn(self.transaction2, account1_transactions)
        self.assertNotIn(self.transaction3, account1_transactions)

        # Test filtering by date range
        date_range_transactions = Transaction.objects.filter_for_table(date_from=self.start_date, date_to=self.end_date)
        self.assertIn(self.transaction1, date_range_transactions)
        self.assertIn(self.transaction2, date_range_transactions)
        self.assertIn(self.transaction3, date_range_transactions)

    def test_get_queryset(self):
        # Test that get_queryset returns a TransactionQuerySet
        self.assertIsInstance(Transaction.objects.get_queryset(), TransactionQuerySet, "get_queryset should return a TransactionQuerySet instance")