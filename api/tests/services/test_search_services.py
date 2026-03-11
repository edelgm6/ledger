import datetime
from decimal import Decimal

from django.test import TestCase

from api.models import (
    Account,
    JournalEntryItem,
    Transaction,
)
from api.services.search_services import (
    apply_bulk_account_change,
    preview_bulk_account_change,
    search_transactions,
)
from api.tests.testing_factories import (
    AccountFactory,
    EntityFactory,
    JournalEntryFactory,
    JournalEntryItemFactory,
    TransactionFactory,
)


class SearchTransactionsTests(TestCase):
    def setUp(self):
        self.account_checking = AccountFactory(
            name="Checking",
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
            is_closed=False,
        )
        self.account_groceries = AccountFactory(
            name="Groceries",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.PURCHASES,
            is_closed=False,
        )
        self.account_premium_groceries = AccountFactory(
            name="Premium Groceries",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.PURCHASES,
            is_closed=False,
        )
        self.entity = EntityFactory(name="Whole Foods")

        # Create transactions with JEs and JEIs
        self.txn1 = TransactionFactory(
            description="Whole Foods Market",
            category="Groceries",
            account=self.account_checking,
            amount=Decimal("-50.00"),
            date=datetime.date(2025, 1, 15),
            is_closed=True,
            type=Transaction.TransactionType.PURCHASE,
        )
        je1 = JournalEntryFactory(transaction=self.txn1, date=self.txn1.date)
        JournalEntryItemFactory(
            journal_entry=je1,
            account=self.account_groceries,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal("50.00"),
            entity=self.entity,
        )
        JournalEntryItemFactory(
            journal_entry=je1,
            account=self.account_checking,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("50.00"),
        )

        self.txn2 = TransactionFactory(
            description="Trader Joes",
            category="Groceries",
            account=self.account_checking,
            amount=Decimal("-30.00"),
            date=datetime.date(2025, 2, 10),
            is_closed=True,
            type=Transaction.TransactionType.PURCHASE,
        )
        je2 = JournalEntryFactory(transaction=self.txn2, date=self.txn2.date)
        JournalEntryItemFactory(
            journal_entry=je2,
            account=self.account_groceries,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal("30.00"),
        )
        JournalEntryItemFactory(
            journal_entry=je2,
            account=self.account_checking,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("30.00"),
        )

        self.txn3 = TransactionFactory(
            description="Amazon Purchase",
            category="Shopping",
            account=self.account_checking,
            amount=Decimal("-100.00"),
            date=datetime.date(2025, 3, 5),
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )

    def test_search_by_description(self):
        result = search_transactions(description="whole foods")
        self.assertEqual(result.count, 1)
        self.assertEqual(result.transactions[0], self.txn1)

    def test_search_by_jei_account(self):
        result = search_transactions(related_accounts=[self.account_groceries])
        self.assertEqual(result.count, 2)

    def test_search_by_date_range(self):
        result = search_transactions(
            date_from=datetime.date(2025, 2, 1),
            date_to=datetime.date(2025, 2, 28),
        )
        self.assertEqual(result.count, 1)
        self.assertEqual(result.transactions[0], self.txn2)

    def test_search_combined_filters(self):
        result = search_transactions(
            description="whole",
            related_accounts=[self.account_groceries],
        )
        self.assertEqual(result.count, 1)
        self.assertEqual(result.transactions[0], self.txn1)

    def test_search_no_results(self):
        result = search_transactions(description="nonexistent")
        self.assertEqual(result.count, 0)

class PreviewBulkAccountChangeTests(TestCase):
    def setUp(self):
        self.account_checking = AccountFactory(
            name="Checking",
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
            is_closed=False,
        )
        self.account_groceries = AccountFactory(
            name="Groceries",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.PURCHASES,
            is_closed=False,
        )
        self.account_premium = AccountFactory(
            name="Premium Groceries",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.PURCHASES,
            is_closed=False,
        )

        self.txn1 = TransactionFactory(
            account=self.account_checking,
            amount=Decimal("-50.00"),
            is_closed=True,
            type=Transaction.TransactionType.PURCHASE,
        )
        je1 = JournalEntryFactory(transaction=self.txn1, date=self.txn1.date)
        JournalEntryItemFactory(
            journal_entry=je1,
            account=self.account_groceries,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal("50.00"),
        )
        JournalEntryItemFactory(
            journal_entry=je1,
            account=self.account_checking,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("50.00"),
        )

        self.txn2 = TransactionFactory(
            account=self.account_checking,
            amount=Decimal("-30.00"),
            is_closed=True,
            type=Transaction.TransactionType.PURCHASE,
        )
        je2 = JournalEntryFactory(transaction=self.txn2, date=self.txn2.date)
        JournalEntryItemFactory(
            journal_entry=je2,
            account=self.account_groceries,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal("30.00"),
        )
        JournalEntryItemFactory(
            journal_entry=je2,
            account=self.account_checking,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("30.00"),
        )

    def test_preview_returns_correct_count(self):
        result = preview_bulk_account_change(
            transactions=[self.txn1, self.txn2],
            from_account=self.account_groceries,
            to_account=self.account_premium,
        )
        self.assertEqual(result.affected_count, 2)
        self.assertEqual(result.from_account, self.account_groceries)
        self.assertEqual(result.to_account, self.account_premium)

    def test_preview_scoped_to_transactions(self):
        """Only counts JEIs within the provided transactions."""
        result = preview_bulk_account_change(
            transactions=[self.txn1],
            from_account=self.account_groceries,
            to_account=self.account_premium,
        )
        self.assertEqual(result.affected_count, 1)

    def test_preview_no_matches(self):
        result = preview_bulk_account_change(
            transactions=[self.txn1, self.txn2],
            from_account=self.account_premium,
            to_account=self.account_groceries,
        )
        self.assertEqual(result.affected_count, 0)


class ApplyBulkAccountChangeTests(TestCase):
    def setUp(self):
        self.account_checking = AccountFactory(
            name="Checking",
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
            is_closed=False,
        )
        self.account_groceries = AccountFactory(
            name="Groceries",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.PURCHASES,
            is_closed=False,
        )
        self.account_premium = AccountFactory(
            name="Premium Groceries",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.PURCHASES,
            is_closed=False,
        )

        self.txn1 = TransactionFactory(
            account=self.account_checking,
            amount=Decimal("-50.00"),
            is_closed=True,
            type=Transaction.TransactionType.PURCHASE,
        )
        je1 = JournalEntryFactory(transaction=self.txn1, date=self.txn1.date)
        self.jei_groceries_1 = JournalEntryItemFactory(
            journal_entry=je1,
            account=self.account_groceries,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal("50.00"),
        )
        self.jei_checking_1 = JournalEntryItemFactory(
            journal_entry=je1,
            account=self.account_checking,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("50.00"),
        )

        self.txn2 = TransactionFactory(
            account=self.account_checking,
            amount=Decimal("-30.00"),
            is_closed=True,
            type=Transaction.TransactionType.PURCHASE,
        )
        je2 = JournalEntryFactory(transaction=self.txn2, date=self.txn2.date)
        self.jei_groceries_2 = JournalEntryItemFactory(
            journal_entry=je2,
            account=self.account_groceries,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal("30.00"),
        )
        self.jei_checking_2 = JournalEntryItemFactory(
            journal_entry=je2,
            account=self.account_checking,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("30.00"),
        )

    def test_apply_updates_matching_jeis(self):
        result = apply_bulk_account_change(
            transactions=[self.txn1, self.txn2],
            from_account_id=self.account_groceries.pk,
            to_account_id=self.account_premium.pk,
        )
        self.assertTrue(result.success)
        self.assertEqual(result.updated_count, 2)

        # Verify JEIs were updated
        self.jei_groceries_1.refresh_from_db()
        self.jei_groceries_2.refresh_from_db()
        self.assertEqual(self.jei_groceries_1.account, self.account_premium)
        self.assertEqual(self.jei_groceries_2.account, self.account_premium)

    def test_apply_leaves_non_matching_jeis_untouched(self):
        apply_bulk_account_change(
            transactions=[self.txn1, self.txn2],
            from_account_id=self.account_groceries.pk,
            to_account_id=self.account_premium.pk,
        )

        # Checking account JEIs should be unchanged
        self.jei_checking_1.refresh_from_db()
        self.jei_checking_2.refresh_from_db()
        self.assertEqual(self.jei_checking_1.account, self.account_checking)
        self.assertEqual(self.jei_checking_2.account, self.account_checking)

    def test_apply_scoped_to_transactions(self):
        """Only updates JEIs within the provided transactions."""
        result = apply_bulk_account_change(
            transactions=[self.txn1],
            from_account_id=self.account_groceries.pk,
            to_account_id=self.account_premium.pk,
        )
        self.assertEqual(result.updated_count, 1)

        # txn1's JEI updated, txn2's JEI unchanged
        self.jei_groceries_1.refresh_from_db()
        self.jei_groceries_2.refresh_from_db()
        self.assertEqual(self.jei_groceries_1.account, self.account_premium)
        self.assertEqual(self.jei_groceries_2.account, self.account_groceries)
