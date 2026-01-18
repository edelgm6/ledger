from decimal import Decimal

from django.test import TestCase

from api.models import Account, Entity, JournalEntryItem
from api.services.entity_services import (
    EntityBalance,
    EntityHistoryData,
    EntityHistoryItem,
    UntaggedItemsData,
    get_entities_balances,
    get_entity_history,
    get_untagged_journal_entry_items,
    tag_journal_entry_item,
    untag_journal_entry_item,
)
from api.tests.testing_factories import (
    AccountFactory,
    EntityFactory,
    JournalEntryFactory,
    JournalEntryItemFactory,
)


class GetEntitiesBalancesTest(TestCase):
    """Tests for get_entities_balances() function."""

    def setUp(self):
        self.ar_account = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.ACCOUNTS_RECEIVABLE,
        )
        self.non_ar_account = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
        )
        self.entity1 = EntityFactory(name="Entity One")
        self.entity2 = EntityFactory(name="Entity Two")

    def test_returns_entity_balances(self):
        """Test returns balances grouped by entity."""
        journal_entry = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.ar_account,
            entity=self.entity1,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("100.00"),
        )

        balances = get_entities_balances()

        self.assertEqual(len(balances), 1)
        self.assertIsInstance(balances[0], EntityBalance)
        self.assertEqual(balances[0].entity_id, self.entity1.id)
        self.assertEqual(balances[0].entity_name, "Entity One")

    def test_calculates_balance_correctly(self):
        """Test balance calculation: credits - debits."""
        journal_entry = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.ar_account,
            entity=self.entity1,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("150.00"),
        )
        JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.ar_account,
            entity=self.entity1,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal("50.00"),
        )

        balances = get_entities_balances()

        self.assertEqual(len(balances), 1)
        self.assertEqual(balances[0].total_credits, Decimal("150.00"))
        self.assertEqual(balances[0].total_debits, Decimal("50.00"))
        self.assertEqual(balances[0].balance, Decimal("100.00"))

    def test_orders_by_absolute_balance_descending(self):
        """Test ordering by absolute balance descending."""
        journal_entry = JournalEntryFactory()
        # Entity1: balance = 50
        JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.ar_account,
            entity=self.entity1,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("50.00"),
        )
        # Entity2: balance = -100 (abs = 100, higher)
        JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.ar_account,
            entity=self.entity2,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal("100.00"),
        )

        balances = get_entities_balances()

        self.assertEqual(len(balances), 2)
        # Entity2 should come first (higher absolute balance)
        self.assertEqual(balances[0].entity_id, self.entity2.id)
        self.assertEqual(balances[1].entity_id, self.entity1.id)

    def test_excludes_items_without_entities(self):
        """Test items without entity assignment are excluded."""
        journal_entry = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.ar_account,
            entity=None,  # No entity
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("100.00"),
        )

        balances = get_entities_balances()

        self.assertEqual(len(balances), 0)

    def test_excludes_non_accounts_receivable(self):
        """Test only accounts receivable items are included."""
        journal_entry = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.non_ar_account,  # Not AR
            entity=self.entity1,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("100.00"),
        )

        balances = get_entities_balances()

        self.assertEqual(len(balances), 0)

    def test_returns_empty_list_when_no_data(self):
        """Test returns empty list when no matching items."""
        balances = get_entities_balances()

        self.assertEqual(balances, [])


class GetUntaggedJournalEntryItemsTest(TestCase):
    """Tests for get_untagged_journal_entry_items() function."""

    def setUp(self):
        self.ar_account = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.ACCOUNTS_RECEIVABLE,
        )
        self.cash_account = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
        )
        self.entity = EntityFactory()

    def test_returns_items_with_null_entity(self):
        """Test returns items without entity assignment."""
        journal_entry = JournalEntryFactory()
        item = JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.ar_account,
            entity=None,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("100.00"),
        )

        result = get_untagged_journal_entry_items()

        self.assertIsInstance(result, UntaggedItemsData)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].id, item.id)

    def test_filters_by_accounts_receivable_sub_type(self):
        """Test only accounts receivable items are returned."""
        journal_entry = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.cash_account,  # Not AR
            entity=None,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("100.00"),
        )

        result = get_untagged_journal_entry_items()

        self.assertEqual(len(result.items), 0)

    def test_excludes_items_with_entity(self):
        """Test items with entity are excluded."""
        journal_entry = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.ar_account,
            entity=self.entity,  # Has entity
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("100.00"),
        )

        result = get_untagged_journal_entry_items()

        self.assertEqual(len(result.items), 0)

    def test_returns_first_item_correctly(self):
        """Test first_item is set correctly."""
        journal_entry = JournalEntryFactory()
        item = JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.ar_account,
            entity=None,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("100.00"),
        )

        result = get_untagged_journal_entry_items()

        self.assertEqual(result.first_item, item)

    def test_first_item_none_when_no_items(self):
        """Test first_item is None when no items exist."""
        result = get_untagged_journal_entry_items()

        self.assertEqual(result.items, [])
        self.assertIsNone(result.first_item)


class GetEntityHistoryTest(TestCase):
    """Tests for get_entity_history() function."""

    def setUp(self):
        self.ar_account = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.ACCOUNTS_RECEIVABLE,
        )
        self.entity = EntityFactory()

    def test_returns_items_for_entity(self):
        """Test returns items for specified entity."""
        journal_entry = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.ar_account,
            entity=self.entity,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("100.00"),
        )

        result = get_entity_history(self.entity.id)

        self.assertIsInstance(result, EntityHistoryData)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.entity_id, self.entity.id)

    def test_calculates_running_balance_correctly(self):
        """Test running balance calculation."""
        journal_entry = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.ar_account,
            entity=self.entity,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("100.00"),
        )
        JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.ar_account,
            entity=self.entity,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal("30.00"),
        )

        result = get_entity_history(self.entity.id)

        self.assertEqual(len(result.items), 2)
        # Running balances depend on order - check both items have valid balances
        balances = [item.running_balance for item in result.items]
        # Credits increase balance, debits decrease
        self.assertIn(Decimal("100.00"), balances)
        self.assertIn(Decimal("70.00"), balances)

    def test_returns_empty_for_no_items(self):
        """Test returns empty list when entity has no items."""
        result = get_entity_history(self.entity.id)

        self.assertEqual(result.items, [])
        self.assertEqual(result.entity_id, self.entity.id)

    def test_returns_entity_history_items(self):
        """Test items are EntityHistoryItem instances."""
        journal_entry = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.ar_account,
            entity=self.entity,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("50.00"),
        )

        result = get_entity_history(self.entity.id)

        self.assertIsInstance(result.items[0], EntityHistoryItem)
        self.assertIsInstance(result.items[0].journal_entry_item, JournalEntryItem)
        self.assertIsInstance(result.items[0].running_balance, Decimal)


class UntagJournalEntryItemTest(TestCase):
    """Tests for untag_journal_entry_item() function."""

    def setUp(self):
        self.account = AccountFactory()
        self.entity = EntityFactory()

    def test_removes_entity_from_item(self):
        """Test entity is removed from journal entry item."""
        journal_entry = JournalEntryFactory()
        item = JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.account,
            entity=self.entity,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("100.00"),
        )

        untag_journal_entry_item(item.id)

        item.refresh_from_db()
        self.assertIsNone(item.entity)

    def test_returns_removed_entity(self):
        """Test returns the entity that was removed."""
        journal_entry = JournalEntryFactory()
        item = JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.account,
            entity=self.entity,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("100.00"),
        )

        result = untag_journal_entry_item(item.id)

        self.assertEqual(result, self.entity)


class TagJournalEntryItemTest(TestCase):
    """Tests for tag_journal_entry_item() function."""

    def setUp(self):
        self.account = AccountFactory()
        self.entity = EntityFactory()

    def test_assigns_entity_to_item(self):
        """Test entity is assigned to journal entry item."""
        journal_entry = JournalEntryFactory()
        item = JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.account,
            entity=None,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("100.00"),
        )

        tag_journal_entry_item(item.id, self.entity.id)

        item.refresh_from_db()
        self.assertEqual(item.entity, self.entity)

    def test_replaces_existing_entity(self):
        """Test can replace existing entity assignment."""
        old_entity = EntityFactory(name="Old Entity")
        journal_entry = JournalEntryFactory()
        item = JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.account,
            entity=old_entity,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("100.00"),
        )

        tag_journal_entry_item(item.id, self.entity.id)

        item.refresh_from_db()
        self.assertEqual(item.entity, self.entity)
