from decimal import Decimal

from django.test import TestCase

from api.models import Account, Entity, JournalEntryItem
from api.services.entity_services import (
    EntityBalance,
    EntityHistoryData,
    EntityHistoryItem,
    GroupedEntityBalances,
    UntaggedItemsData,
    get_entities_balances,
    get_entity_history,
    get_grouped_entities_balances,
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


class GetGroupedEntitiesBalancesTest(TestCase):
    """Tests for get_grouped_entities_balances() function."""

    def setUp(self):
        self.ar_account = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.ACCOUNTS_RECEIVABLE,
            is_closed=False,
        )
        self.non_ar_account = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
        )
        self.entity1 = EntityFactory(name="Entity One")
        self.entity2 = EntityFactory(name="Entity Two")

    def _make_item(self, account, entity, type, amount):
        je = JournalEntryFactory()
        return JournalEntryItemFactory(
            journal_entry=je, account=account, entity=entity,
            type=type, amount=Decimal(amount),
        )

    def test_returns_grouped_entity_balances_instances(self):
        self._make_item(self.ar_account, self.entity1, JournalEntryItem.JournalEntryType.CREDIT, "100.00")

        result = get_grouped_entities_balances()

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], GroupedEntityBalances)

    def test_groups_by_account(self):
        ar_account2 = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.ACCOUNTS_RECEIVABLE,
        )
        self._make_item(self.ar_account, self.entity1, JournalEntryItem.JournalEntryType.CREDIT, "100.00")
        self._make_item(ar_account2, self.entity2, JournalEntryItem.JournalEntryType.CREDIT, "200.00")

        result = get_grouped_entities_balances()

        self.assertEqual(len(result), 2)
        account_ids = {g.account_id for g in result}
        self.assertIn(self.ar_account.id, account_ids)
        self.assertIn(ar_account2.id, account_ids)

    def test_calculates_net_balance_per_group(self):
        self._make_item(self.ar_account, self.entity1, JournalEntryItem.JournalEntryType.CREDIT, "100.00")
        self._make_item(self.ar_account, self.entity2, JournalEntryItem.JournalEntryType.DEBIT, "40.00")

        result = get_grouped_entities_balances(hide_zero=False)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].net_balance, Decimal("60.00"))

    def test_hide_zero_true_excludes_zero_balance_entities(self):
        # entity1: zero balance (credit and debit cancel)
        je = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=je, account=self.ar_account, entity=self.entity1,
            type=JournalEntryItem.JournalEntryType.CREDIT, amount=Decimal("50.00"),
        )
        JournalEntryItemFactory(
            journal_entry=je, account=self.ar_account, entity=self.entity1,
            type=JournalEntryItem.JournalEntryType.DEBIT, amount=Decimal("50.00"),
        )
        # entity2: non-zero balance
        self._make_item(self.ar_account, self.entity2, JournalEntryItem.JournalEntryType.CREDIT, "100.00")

        result = get_grouped_entities_balances(hide_zero=True)

        self.assertEqual(len(result[0].rows), 1)
        self.assertEqual(result[0].rows[0].entity_id, self.entity2.id)
        self.assertEqual(result[0].zero_count, 1)

    def test_hide_zero_false_includes_all_entities(self):
        je = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=je, account=self.ar_account, entity=self.entity1,
            type=JournalEntryItem.JournalEntryType.CREDIT, amount=Decimal("50.00"),
        )
        JournalEntryItemFactory(
            journal_entry=je, account=self.ar_account, entity=self.entity1,
            type=JournalEntryItem.JournalEntryType.DEBIT, amount=Decimal("50.00"),
        )
        self._make_item(self.ar_account, self.entity2, JournalEntryItem.JournalEntryType.CREDIT, "100.00")

        result = get_grouped_entities_balances(hide_zero=False)

        self.assertEqual(len(result[0].rows), 2)
        self.assertEqual(result[0].zero_count, 0)

    def test_excludes_non_ar_accounts(self):
        self._make_item(self.non_ar_account, self.entity1, JournalEntryItem.JournalEntryType.CREDIT, "100.00")

        result = get_grouped_entities_balances()

        self.assertEqual(result, [])

    def test_excludes_items_without_entity(self):
        je = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=je, account=self.ar_account, entity=None,
            type=JournalEntryItem.JournalEntryType.CREDIT, amount=Decimal("100.00"),
        )

        result = get_grouped_entities_balances()

        self.assertEqual(result, [])

    def test_returns_empty_when_no_data(self):
        self.assertEqual(get_grouped_entities_balances(), [])

    def test_closed_account_with_all_zero_balances_excluded_when_hide_zero(self):
        closed_account = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.ACCOUNTS_RECEIVABLE,
            is_closed=True,
        )
        je = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=je, account=closed_account, entity=self.entity1,
            type=JournalEntryItem.JournalEntryType.CREDIT, amount=Decimal("50.00"),
        )
        JournalEntryItemFactory(
            journal_entry=je, account=closed_account, entity=self.entity1,
            type=JournalEntryItem.JournalEntryType.DEBIT, amount=Decimal("50.00"),
        )

        result = get_grouped_entities_balances(hide_zero=True)

        account_ids = [g.account_id for g in result]
        self.assertNotIn(closed_account.id, account_ids)

    def test_closed_account_with_all_zero_balances_included_when_not_hide_zero(self):
        closed_account = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.ACCOUNTS_RECEIVABLE,
            is_closed=True,
        )
        je = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=je, account=closed_account, entity=self.entity1,
            type=JournalEntryItem.JournalEntryType.CREDIT, amount=Decimal("50.00"),
        )
        JournalEntryItemFactory(
            journal_entry=je, account=closed_account, entity=self.entity1,
            type=JournalEntryItem.JournalEntryType.DEBIT, amount=Decimal("50.00"),
        )

        result = get_grouped_entities_balances(hide_zero=False)

        account_ids = [g.account_id for g in result]
        self.assertIn(closed_account.id, account_ids)

    def test_closed_account_with_nonzero_balance_always_included(self):
        closed_account = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.ACCOUNTS_RECEIVABLE,
            is_closed=True,
        )
        self._make_item(closed_account, self.entity1, JournalEntryItem.JournalEntryType.CREDIT, "100.00")

        result = get_grouped_entities_balances(hide_zero=True)

        account_ids = [g.account_id for g in result]
        self.assertIn(closed_account.id, account_ids)

    def test_open_account_with_all_zero_balances_still_shown_when_hide_zero(self):
        je = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=je, account=self.ar_account, entity=self.entity1,
            type=JournalEntryItem.JournalEntryType.CREDIT, amount=Decimal("50.00"),
        )
        JournalEntryItemFactory(
            journal_entry=je, account=self.ar_account, entity=self.entity1,
            type=JournalEntryItem.JournalEntryType.DEBIT, amount=Decimal("50.00"),
        )

        result = get_grouped_entities_balances(hide_zero=True)

        account_ids = [g.account_id for g in result]
        self.assertIn(self.ar_account.id, account_ids)
        self.assertEqual(result[0].rows, [])
        self.assertEqual(result[0].zero_count, 1)


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

    def test_populates_entity_name(self):
        journal_entry = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.ar_account,
            entity=self.entity,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("100.00"),
        )

        result = get_entity_history(self.entity.id)

        self.assertEqual(result.entity_name, self.entity.name)

    def test_entity_name_empty_when_no_items(self):
        result = get_entity_history(self.entity.id)

        self.assertEqual(result.entity_name, "")

    def test_account_id_scopes_history_to_that_account(self):
        ar_account2 = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.ACCOUNTS_RECEIVABLE,
        )
        je = JournalEntryFactory()
        item_account1 = JournalEntryItemFactory(
            journal_entry=je,
            account=self.ar_account,
            entity=self.entity,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("100.00"),
        )
        JournalEntryItemFactory(
            journal_entry=je,
            account=ar_account2,
            entity=self.entity,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("200.00"),
        )

        result = get_entity_history(self.entity.id, account_id=self.ar_account.id)

        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].journal_entry_item.id, item_account1.id)

    def test_account_name_set_when_account_id_provided(self):
        je = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=je,
            account=self.ar_account,
            entity=self.entity,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("100.00"),
        )

        result = get_entity_history(self.entity.id, account_id=self.ar_account.id)

        self.assertEqual(result.account_name, self.ar_account.name)

    def test_account_name_none_when_no_account_id(self):
        je = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=je,
            account=self.ar_account,
            entity=self.entity,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("100.00"),
        )

        result = get_entity_history(self.entity.id)

        self.assertIsNone(result.account_name)

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
