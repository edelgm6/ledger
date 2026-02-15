from decimal import Decimal

from django.test import TestCase

from api.models import Account, Entity, JournalEntry, JournalEntryItem, Transaction
from api.services.rest_api_services import (
    bulk_create_journal_entries,
    create_journal_entry_from_api,
    resolve_names_to_objects,
)
from api.tests.testing_factories import AccountFactory, EntityFactory, TransactionFactory


class ResolveNamesToObjectsTest(TestCase):
    def test_resolves_account_names(self):
        account = AccountFactory(name="Checking")
        accounts_map = {"Checking": account}
        entities_map = {}
        created_entities = []

        items = [{"account": "Checking", "amount": "100.00"}]
        resolved = resolve_names_to_objects(
            items, accounts_map, entities_map, created_entities
        )
        self.assertEqual(resolved[0]["account"], account)
        self.assertEqual(resolved[0]["amount"], Decimal("100.00"))

    def test_raises_on_unknown_account(self):
        items = [{"account": "Nonexistent", "amount": "100.00"}]
        with self.assertRaises(ValueError) as ctx:
            resolve_names_to_objects(items, {}, {}, [])
        self.assertIn("not found", str(ctx.exception))

    def test_auto_creates_entity(self):
        account = AccountFactory(name="Groceries")
        accounts_map = {"Groceries": account}
        entities_map = {}
        created_entities = []

        items = [{"account": "Groceries", "amount": "50.00", "entity": "New Store"}]
        resolved = resolve_names_to_objects(
            items, accounts_map, entities_map, created_entities
        )
        self.assertEqual(resolved[0]["entity"].name, "New Store")
        self.assertIn("New Store", created_entities)
        self.assertTrue(Entity.objects.filter(name="New Store").exists())

    def test_reuses_existing_entity(self):
        entity = EntityFactory(name="Existing Store")
        account = AccountFactory(name="Groceries")
        accounts_map = {"Groceries": account}
        entities_map = {"Existing Store": entity}
        created_entities = []

        items = [
            {"account": "Groceries", "amount": "50.00", "entity": "Existing Store"}
        ]
        resolved = resolve_names_to_objects(
            items, accounts_map, entities_map, created_entities
        )
        self.assertEqual(resolved[0]["entity"], entity)
        self.assertEqual(len(created_entities), 0)


class CreateJournalEntryFromAPITest(TestCase):
    def setUp(self):
        self.checking = AccountFactory(
            name="Checking",
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
        )
        self.groceries = AccountFactory(
            name="Groceries",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.PURCHASES,
        )

    def test_creates_journal_entry(self):
        transaction = TransactionFactory(
            account=self.checking,
            amount=Decimal("100.00"),
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )
        result = create_journal_entry_from_api(
            transaction_id=transaction.id,
            debits_data=[{"account": "Checking", "amount": "100.00"}],
            credits_data=[{"account": "Groceries", "amount": "100.00"}],
            created_by="test",
        )
        self.assertIn("journal_entry_id", result)
        self.assertEqual(result["created_by"], "test")

        je = JournalEntry.objects.get(pk=result["journal_entry_id"])
        self.assertEqual(je.created_by, "test")
        self.assertEqual(
            JournalEntryItem.objects.filter(journal_entry=je).count(), 2
        )

    def test_creates_journal_entry_items_with_correct_types_and_amounts(self):
        transaction = TransactionFactory(
            account=self.checking,
            amount=Decimal("100.00"),
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )
        result = create_journal_entry_from_api(
            transaction_id=transaction.id,
            debits_data=[{"account": "Checking", "amount": "100.00"}],
            credits_data=[{"account": "Groceries", "amount": "100.00"}],
        )
        je = JournalEntry.objects.get(pk=result["journal_entry_id"])
        items = JournalEntryItem.objects.filter(journal_entry=je)

        debit_items = items.filter(type=JournalEntryItem.JournalEntryType.DEBIT)
        credit_items = items.filter(type=JournalEntryItem.JournalEntryType.CREDIT)
        self.assertEqual(debit_items.count(), 1)
        self.assertEqual(credit_items.count(), 1)
        self.assertEqual(debit_items.first().account, self.checking)
        self.assertEqual(debit_items.first().amount, Decimal("100.00"))
        self.assertEqual(credit_items.first().account, self.groceries)
        self.assertEqual(credit_items.first().amount, Decimal("100.00"))

    def test_raises_on_unbalanced_debits_and_credits(self):
        transaction = TransactionFactory(
            account=self.checking,
            amount=Decimal("100.00"),
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )
        with self.assertRaises(ValueError) as ctx:
            create_journal_entry_from_api(
                transaction_id=transaction.id,
                debits_data=[{"account": "Checking", "amount": "100.00"}],
                credits_data=[{"account": "Groceries", "amount": "50.00"}],
            )
        self.assertIn("must balance", str(ctx.exception).lower())

    def test_creates_with_negative_transaction_amount(self):
        """Negative amount: transaction account should be on the credit side."""
        transaction = TransactionFactory(
            account=self.checking,
            amount=Decimal("-75.00"),
            is_closed=False,
            type=Transaction.TransactionType.INCOME,
        )
        result = create_journal_entry_from_api(
            transaction_id=transaction.id,
            debits_data=[{"account": "Groceries", "amount": "75.00"}],
            credits_data=[{"account": "Checking", "amount": "75.00"}],
        )
        je = JournalEntry.objects.get(pk=result["journal_entry_id"])
        items = JournalEntryItem.objects.filter(journal_entry=je)

        debit_items = items.filter(type=JournalEntryItem.JournalEntryType.DEBIT)
        credit_items = items.filter(type=JournalEntryItem.JournalEntryType.CREDIT)
        self.assertEqual(debit_items.first().account, self.groceries)
        self.assertEqual(credit_items.first().account, self.checking)

    def test_creates_split_entry_multiple_debits(self):
        """Split transaction: 2 debits, 1 credit."""
        rent = AccountFactory(
            name="Rent",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.PURCHASES,
        )
        transaction = TransactionFactory(
            account=self.checking,
            amount=Decimal("200.00"),
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )
        result = create_journal_entry_from_api(
            transaction_id=transaction.id,
            debits_data=[
                {"account": "Checking", "amount": "200.00"},
                {"account": "Rent", "amount": "0.01"},
            ],
            credits_data=[
                {"account": "Groceries", "amount": "200.00"},
                {"account": "Rent", "amount": "0.01"},
            ],
        )
        je = JournalEntry.objects.get(pk=result["journal_entry_id"])
        self.assertEqual(
            JournalEntryItem.objects.filter(journal_entry=je).count(), 4
        )

    def test_raises_on_nonexistent_transaction(self):
        with self.assertRaises(ValueError):
            create_journal_entry_from_api(
                transaction_id=99999,
                debits_data=[{"account": "Groceries", "amount": "100.00"}],
                credits_data=[{"account": "Checking", "amount": "100.00"}],
            )

    def test_raises_on_closed_transaction(self):
        transaction = TransactionFactory(
            account=self.checking,
            amount=Decimal("100.00"),
            is_closed=True,
        )
        with self.assertRaises(ValueError) as ctx:
            create_journal_entry_from_api(
                transaction_id=transaction.id,
                debits_data=[{"account": "Groceries", "amount": "100.00"}],
                credits_data=[{"account": "Checking", "amount": "100.00"}],
            )
        self.assertIn("already closed", str(ctx.exception))


class BulkCreateJournalEntriesTest(TestCase):
    def setUp(self):
        self.checking = AccountFactory(
            name="Checking",
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
        )
        self.groceries = AccountFactory(
            name="Groceries",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.PURCHASES,
        )

    def test_bulk_creates_multiple_entries(self):
        t1 = TransactionFactory(
            account=self.checking,
            amount=Decimal("100.00"),
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )
        t2 = TransactionFactory(
            account=self.checking,
            amount=Decimal("200.00"),
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )
        entries_data = [
            {
                "transaction_id": t1.id,
                "created_by": "Claude",
                "debits": [{"account": "Checking", "amount": "100.00"}],
                "credits": [{"account": "Groceries", "amount": "100.00"}],
            },
            {
                "transaction_id": t2.id,
                "created_by": "Claude",
                "debits": [{"account": "Checking", "amount": "200.00"}],
                "credits": [{"account": "Groceries", "amount": "200.00"}],
            },
        ]
        result = bulk_create_journal_entries(entries_data)
        self.assertEqual(result["count"], 2)

    def test_bulk_entity_created_in_first_entry_reused_in_second(self):
        t1 = TransactionFactory(
            account=self.checking,
            amount=Decimal("100.00"),
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )
        t2 = TransactionFactory(
            account=self.checking,
            amount=Decimal("200.00"),
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )
        entries_data = [
            {
                "transaction_id": t1.id,
                "debits": [{"account": "Checking", "amount": "100.00", "entity": "New Corp"}],
                "credits": [{"account": "Groceries", "amount": "100.00"}],
            },
            {
                "transaction_id": t2.id,
                "debits": [{"account": "Checking", "amount": "200.00", "entity": "New Corp"}],
                "credits": [{"account": "Groceries", "amount": "200.00"}],
            },
        ]
        result = bulk_create_journal_entries(entries_data)
        self.assertEqual(result["count"], 2)
        # Entity should only be created once
        self.assertEqual(Entity.objects.filter(name="New Corp").count(), 1)
        self.assertEqual(result["created_entities"].count("New Corp"), 1)

    def test_bulk_rolls_back_on_failure(self):
        t1 = TransactionFactory(
            account=self.checking,
            amount=Decimal("100.00"),
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )
        entries_data = [
            {
                "transaction_id": t1.id,
                "created_by": "Claude",
                "debits": [{"account": "Checking", "amount": "100.00"}],
                "credits": [{"account": "Groceries", "amount": "100.00"}],
            },
            {
                "transaction_id": 99999,
                "debits": [{"account": "Groceries", "amount": "100.00"}],
                "credits": [{"account": "Checking", "amount": "100.00"}],
            },
        ]
        with self.assertRaises(ValueError):
            bulk_create_journal_entries(entries_data)

        # First transaction should not be closed
        t1.refresh_from_db()
        self.assertFalse(t1.is_closed)
        self.assertEqual(JournalEntry.objects.count(), 0)
