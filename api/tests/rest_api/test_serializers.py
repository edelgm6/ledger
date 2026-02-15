from decimal import Decimal

from django.test import TestCase

from api.models import Account, JournalEntry
from api.rest_api.serializers import (
    AccountSerializer,
    BulkJournalEntryInputSerializer,
    JournalEntryInputSerializer,
    TransactionSerializer,
)
from api.tests.testing_factories import (
    AccountFactory,
    JournalEntryFactory,
    TransactionFactory,
)


class TransactionSerializerTest(TestCase):
    def test_serializes_transaction_with_account_names(self):
        account = AccountFactory(name="Checking")
        suggested = AccountFactory(name="Groceries")
        transaction = TransactionFactory(
            account=account,
            suggested_account=suggested,
            amount=Decimal("100.00"),
        )
        serializer = TransactionSerializer(transaction)
        data = serializer.data
        self.assertEqual(data["account"], "Checking")
        self.assertEqual(data["suggested_account"], "Groceries")
        self.assertIsNone(data["journal_entry_id"])

    def test_serializes_journal_entry_id_when_exists(self):
        transaction = TransactionFactory()
        je = JournalEntryFactory(transaction=transaction)
        # Refresh to load the reverse relation
        transaction.refresh_from_db()
        serializer = TransactionSerializer(transaction)
        self.assertEqual(serializer.data["journal_entry_id"], je.id)

    def test_suggested_account_none(self):
        transaction = TransactionFactory(suggested_account=None)
        serializer = TransactionSerializer(transaction)
        self.assertIsNone(serializer.data["suggested_account"])


class AccountSerializerTest(TestCase):
    def test_serializes_account_fields(self):
        account = AccountFactory(
            name="Test Account",
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
            is_closed=False,
        )
        serializer = AccountSerializer(account)
        data = serializer.data
        self.assertEqual(data["name"], "Test Account")
        self.assertEqual(data["type"], "asset")
        self.assertEqual(data["sub_type"], "cash")
        self.assertFalse(data["is_closed"])


class JournalEntryInputSerializerTest(TestCase):
    def test_valid_input(self):
        data = {
            "transaction_id": 1,
            "debits": [{"account": "Groceries", "amount": "100.00"}],
            "credits": [{"account": "Checking", "amount": "100.00"}],
            "created_by": "Claude",
        }
        serializer = JournalEntryInputSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["created_by"], "Claude")

    def test_default_created_by(self):
        data = {
            "transaction_id": 1,
            "debits": [{"account": "Groceries", "amount": "100.00"}],
            "credits": [{"account": "Checking", "amount": "100.00"}],
        }
        serializer = JournalEntryInputSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["created_by"], "user")

    def test_invalid_amount_zero(self):
        data = {
            "transaction_id": 1,
            "debits": [{"account": "Groceries", "amount": "0.00"}],
            "credits": [{"account": "Checking", "amount": "100.00"}],
        }
        serializer = JournalEntryInputSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_empty_debits_invalid(self):
        data = {
            "transaction_id": 1,
            "debits": [],
            "credits": [{"account": "Checking", "amount": "100.00"}],
        }
        serializer = JournalEntryInputSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_entity_optional(self):
        data = {
            "transaction_id": 1,
            "debits": [
                {"account": "Groceries", "amount": "100.00", "entity": "Whole Foods"}
            ],
            "credits": [{"account": "Checking", "amount": "100.00"}],
        }
        serializer = JournalEntryInputSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["debits"][0]["entity"], "Whole Foods"
        )


class BulkJournalEntryInputSerializerTest(TestCase):
    def test_valid_bulk_input(self):
        data = {
            "journal_entries": [
                {
                    "transaction_id": 1,
                    "debits": [{"account": "Groceries", "amount": "100.00"}],
                    "credits": [{"account": "Checking", "amount": "100.00"}],
                },
                {
                    "transaction_id": 2,
                    "debits": [{"account": "Rent", "amount": "1500.00"}],
                    "credits": [{"account": "Checking", "amount": "1500.00"}],
                },
            ]
        }
        serializer = BulkJournalEntryInputSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(len(serializer.validated_data["journal_entries"]), 2)

    def test_empty_journal_entries_invalid(self):
        data = {"journal_entries": []}
        serializer = BulkJournalEntryInputSerializer(data=data)
        self.assertFalse(serializer.is_valid())
