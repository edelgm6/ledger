from django.test import TestCase
from decimal import Decimal
from api.models import JournalEntry, JournalEntryItem, Transaction, Account
from api.tests.testing_factories import JournalEntryFactory, JournalEntryItemFactory, TransactionFactory, AccountFactory

class JournalEntryModelTest(TestCase):

    def setUp(self):
        self.transaction = TransactionFactory()
        self.journal_entry = JournalEntryFactory(transaction=self.transaction)

    def test_journal_entry_creation(self):
        """Test the creation of a JournalEntry instance."""
        self.assertIsNotNone(self.journal_entry.pk, "Should create a JournalEntry instance")

    def test_journal_entry_str_representation(self):
        """Test the string representation of the JournalEntry model."""
        expected_representation = f"{self.journal_entry.pk}: {self.journal_entry.date} {self.journal_entry.description}"
        self.assertEqual(str(self.journal_entry), expected_representation, "String representation should be correct")

    def test_delete_journal_entry_items(self):
        """Test the delete_journal_entry_items method of the JournalEntry model."""
        # Create a JournalEntryItem linked to the JournalEntry
        journal_entry_item = JournalEntryItemFactory(journal_entry=self.journal_entry)

        # Delete all JournalEntryItems linked to the JournalEntry
        self.journal_entry.delete_journal_entry_items()

        # Verify that no JournalEntryItems are linked to the JournalEntry
        self.assertFalse(JournalEntryItem.objects.filter(journal_entry=self.journal_entry).exists(), "All JournalEntryItems should be deleted")

class JournalEntryItemModelTest(TestCase):

    def setUp(self):
        self.account = AccountFactory()
        self.journal_entry = JournalEntryFactory()
        self.journal_entry_item = JournalEntryItemFactory(journal_entry=self.journal_entry, account=self.account)

    def test_journal_entry_item_creation(self):
        """Test the creation of a JournalEntryItem instance."""
        self.assertIsNotNone(self.journal_entry_item.pk, "Should create a JournalEntryItem instance")

    def test_journal_entry_item_str_representation(self):
        """Test the string representation of the JournalEntryItem model."""
        expected_representation = f"{self.journal_entry_item.journal_entry.id} {self.journal_entry_item.type} ${self.journal_entry_item.amount}"
        self.assertEqual(str(self.journal_entry_item), expected_representation, "String representation should be correct")


