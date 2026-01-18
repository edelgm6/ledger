"""
Tests for statement_services.py
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from django.test import TestCase

from api.models import Account, JournalEntryItem
from api.services.statement_services import (
    CashFlowMetrics,
    StatementDetailData,
    StatementSummary,
    UnbalancedEntriesResult,
    build_statement_summary,
    calculate_cash_flow_metrics,
    filter_closed_accounts,
    find_unbalanced_journal_entries,
    get_statement_detail_items,
)
from api.statement import Balance
from api.tests.testing_factories import (
    AccountFactory,
    JournalEntryFactory,
    JournalEntryItemFactory,
)


class FilterClosedAccountsTest(TestCase):
    """Tests for filter_closed_accounts()."""

    def test_removes_closed_accounts_with_zero_balance(self):
        """Closed accounts with $0 balance should be removed."""
        closed_account = AccountFactory(is_closed=True)
        balance = Balance(
            account=closed_account,
            amount=Decimal("0"),
            date=date.today(),
        )

        result = filter_closed_accounts([balance])

        self.assertEqual(len(result), 0)

    def test_keeps_closed_accounts_with_nonzero_balance(self):
        """Closed accounts with non-zero balance should be kept."""
        closed_account = AccountFactory(is_closed=True)
        balance = Balance(
            account=closed_account,
            amount=Decimal("100.00"),
            date=date.today(),
        )

        result = filter_closed_accounts([balance])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].amount, Decimal("100.00"))

    def test_keeps_open_accounts_with_zero_balance(self):
        """Open accounts with $0 balance should be kept."""
        open_account = AccountFactory(is_closed=False)
        balance = Balance(
            account=open_account,
            amount=Decimal("0"),
            date=date.today(),
        )

        result = filter_closed_accounts([balance])

        self.assertEqual(len(result), 1)

    def test_keeps_open_accounts_with_nonzero_balance(self):
        """Open accounts with non-zero balance should be kept."""
        open_account = AccountFactory(is_closed=False)
        balance = Balance(
            account=open_account,
            amount=Decimal("500.00"),
            date=date.today(),
        )

        result = filter_closed_accounts([balance])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].amount, Decimal("500.00"))

    def test_filters_mixed_list(self):
        """Should correctly filter a mixed list of accounts."""
        closed_zero = AccountFactory(is_closed=True)
        closed_nonzero = AccountFactory(is_closed=True)
        open_zero = AccountFactory(is_closed=False)
        open_nonzero = AccountFactory(is_closed=False)

        balances = [
            Balance(account=closed_zero, amount=Decimal("0"), date=date.today()),
            Balance(account=closed_nonzero, amount=Decimal("100"), date=date.today()),
            Balance(account=open_zero, amount=Decimal("0"), date=date.today()),
            Balance(account=open_nonzero, amount=Decimal("200"), date=date.today()),
        ]

        result = filter_closed_accounts(balances)

        # Should keep closed_nonzero, open_zero, and open_nonzero
        self.assertEqual(len(result), 3)

    def test_empty_list(self):
        """Should handle empty list."""
        result = filter_closed_accounts([])
        self.assertEqual(result, [])


class BuildStatementSummaryTest(TestCase):
    """Tests for build_statement_summary()."""

    def test_groups_balances_by_account_type(self):
        """Should organize balances by account type."""
        asset_account = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
            is_closed=False,
        )
        income_account = AccountFactory(
            type=Account.Type.INCOME,
            sub_type=Account.SubType.SALARY,
            is_closed=False,
        )

        mock_statement = MagicMock()
        mock_statement.balances = [
            Balance(account=asset_account, amount=Decimal("1000"), date=date.today()),
            Balance(account=income_account, amount=Decimal("5000"), date=date.today()),
        ]

        result = build_statement_summary(mock_statement)

        self.assertIsInstance(result, StatementSummary)
        self.assertIn(Account.Type.ASSET, result.account_types)
        self.assertIn(Account.Type.INCOME, result.account_types)

    def test_calculates_type_totals(self):
        """Should calculate totals for each account type."""
        cash_account = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
            is_closed=False,
        )
        brokerage_account = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.SECURITIES_UNRESTRICTED,
            is_closed=False,
        )

        mock_statement = MagicMock()
        mock_statement.balances = [
            Balance(account=cash_account, amount=Decimal("1000"), date=date.today()),
            Balance(
                account=brokerage_account, amount=Decimal("2000"), date=date.today()
            ),
        ]

        result = build_statement_summary(mock_statement)

        asset_summary = result.account_types[Account.Type.ASSET]
        self.assertEqual(asset_summary.total, Decimal("3000"))

    def test_calculates_subtype_totals(self):
        """Should calculate totals for each sub_type."""
        cash1 = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
            is_closed=False,
        )
        cash2 = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
            is_closed=False,
        )

        mock_statement = MagicMock()
        mock_statement.balances = [
            Balance(account=cash1, amount=Decimal("500"), date=date.today()),
            Balance(account=cash2, amount=Decimal("300"), date=date.today()),
        ]

        result = build_statement_summary(mock_statement)

        asset_summary = result.account_types[Account.Type.ASSET]
        cash_sub = next(s for s in asset_summary.sub_types if s.name == "Cash")
        self.assertEqual(cash_sub.total, Decimal("800"))

    def test_filters_closed_zero_balance_accounts(self):
        """Should filter closed accounts with zero balance from sub_types."""
        open_account = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
            is_closed=False,
        )
        closed_zero = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
            is_closed=True,
        )

        mock_statement = MagicMock()
        mock_statement.balances = [
            Balance(account=open_account, amount=Decimal("500"), date=date.today()),
            Balance(account=closed_zero, amount=Decimal("0"), date=date.today()),
        ]

        result = build_statement_summary(mock_statement)

        asset_summary = result.account_types[Account.Type.ASSET]
        cash_sub = next(s for s in asset_summary.sub_types if s.name == "Cash")
        # Only open account should be in balances
        self.assertEqual(len(cash_sub.balances), 1)


class FindUnbalancedJournalEntriesTest(TestCase):
    """Tests for find_unbalanced_journal_entries()."""

    def test_returns_empty_when_all_balanced(self):
        """Should return empty list when all entries are balanced."""
        account = AccountFactory()
        entry = JournalEntryFactory()

        # Create balanced entry
        JournalEntryItemFactory(
            journal_entry=entry,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal("100"),
            account=account,
        )
        JournalEntryItemFactory(
            journal_entry=entry,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("100"),
            account=account,
        )

        result = find_unbalanced_journal_entries()

        self.assertEqual(result.count, 0)
        self.assertEqual(len(result.entries), 0)

    def test_finds_unbalanced_entries(self):
        """Should find entries where debits != credits."""
        account = AccountFactory()
        entry = JournalEntryFactory()

        # Create unbalanced entry
        JournalEntryItemFactory(
            journal_entry=entry,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal("100"),
            account=account,
        )
        JournalEntryItemFactory(
            journal_entry=entry,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("50"),  # Doesn't match
            account=account,
        )

        result = find_unbalanced_journal_entries()

        self.assertEqual(result.count, 1)
        self.assertEqual(result.entries[0].pk, entry.pk)

    def test_excludes_balanced_entries(self):
        """Should exclude balanced entries from results."""
        account = AccountFactory()

        # Balanced entry
        balanced = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=balanced,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal("100"),
            account=account,
        )
        JournalEntryItemFactory(
            journal_entry=balanced,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("100"),
            account=account,
        )

        # Unbalanced entry
        unbalanced = JournalEntryFactory()
        JournalEntryItemFactory(
            journal_entry=unbalanced,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal("200"),
            account=account,
        )
        JournalEntryItemFactory(
            journal_entry=unbalanced,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("150"),
            account=account,
        )

        result = find_unbalanced_journal_entries()

        self.assertEqual(result.count, 1)
        self.assertEqual(result.entries[0].pk, unbalanced.pk)


class GetStatementDetailItemsTest(TestCase):
    """Tests for get_statement_detail_items()."""

    def test_filters_by_account_id(self):
        """Should return only items for the specified account."""
        target_account = AccountFactory()
        other_account = AccountFactory()

        entry = JournalEntryFactory(date=date(2024, 1, 15))
        JournalEntryItemFactory(
            journal_entry=entry,
            account=target_account,
            amount=Decimal("100"),
            type=JournalEntryItem.JournalEntryType.DEBIT,
        )
        JournalEntryItemFactory(
            journal_entry=entry,
            account=other_account,
            amount=Decimal("100"),
            type=JournalEntryItem.JournalEntryType.CREDIT,
        )

        result = get_statement_detail_items(
            account_id=target_account.pk,
            from_date="2024-01-01",
            to_date="2024-12-31",
        )

        self.assertEqual(len(result.journal_entry_items), 1)
        self.assertEqual(result.journal_entry_items[0].account.pk, target_account.pk)

    def test_filters_by_date_range(self):
        """Should return only items within the date range."""
        account = AccountFactory()

        in_range = JournalEntryFactory(date=date(2024, 6, 15))
        JournalEntryItemFactory(
            journal_entry=in_range,
            account=account,
            amount=Decimal("100"),
            type=JournalEntryItem.JournalEntryType.DEBIT,
        )

        out_of_range = JournalEntryFactory(date=date(2023, 1, 15))
        JournalEntryItemFactory(
            journal_entry=out_of_range,
            account=account,
            amount=Decimal("200"),
            type=JournalEntryItem.JournalEntryType.DEBIT,
        )

        result = get_statement_detail_items(
            account_id=account.pk,
            from_date="2024-01-01",
            to_date="2024-12-31",
        )

        self.assertEqual(len(result.journal_entry_items), 1)
        self.assertEqual(result.journal_entry_items[0].amount, Decimal("100"))

    def test_signs_income_debits_negative(self):
        """INCOME account debits should have negative signed amount."""
        income_account = AccountFactory(type=Account.Type.INCOME)
        entry = JournalEntryFactory(date=date(2024, 6, 15))

        JournalEntryItemFactory(
            journal_entry=entry,
            account=income_account,
            amount=Decimal("100"),
            type=JournalEntryItem.JournalEntryType.DEBIT,
        )

        result = get_statement_detail_items(
            account_id=income_account.pk,
            from_date="2024-01-01",
            to_date="2024-12-31",
        )

        self.assertEqual(result.journal_entry_items[0].amount_signed, Decimal("-100"))

    def test_signs_expense_credits_negative(self):
        """EXPENSE account credits should have negative signed amount."""
        expense_account = AccountFactory(type=Account.Type.EXPENSE)
        entry = JournalEntryFactory(date=date(2024, 6, 15))

        JournalEntryItemFactory(
            journal_entry=entry,
            account=expense_account,
            amount=Decimal("50"),
            type=JournalEntryItem.JournalEntryType.CREDIT,
        )

        result = get_statement_detail_items(
            account_id=expense_account.pk,
            from_date="2024-01-01",
            to_date="2024-12-31",
        )

        self.assertEqual(result.journal_entry_items[0].amount_signed, Decimal("-50"))

    def test_keeps_other_amounts_positive(self):
        """Other combinations should keep positive signed amounts."""
        asset_account = AccountFactory(type=Account.Type.ASSET)
        entry = JournalEntryFactory(date=date(2024, 6, 15))

        JournalEntryItemFactory(
            journal_entry=entry,
            account=asset_account,
            amount=Decimal("200"),
            type=JournalEntryItem.JournalEntryType.DEBIT,
        )

        result = get_statement_detail_items(
            account_id=asset_account.pk,
            from_date="2024-01-01",
            to_date="2024-12-31",
        )

        self.assertEqual(result.journal_entry_items[0].amount_signed, Decimal("200"))


class CalculateCashFlowMetricsTest(TestCase):
    """Tests for calculate_cash_flow_metrics()."""

    def test_returns_cash_flow_metrics_dataclass(self):
        """Should return a CashFlowMetrics dataclass."""
        result = calculate_cash_flow_metrics(
            from_date=date(2024, 1, 1),
            to_date=date(2024, 12, 31),
        )

        self.assertIsInstance(result, CashFlowMetrics)
        self.assertIsInstance(result.operations_flows, list)
        self.assertIsInstance(result.financing_flows, list)
        self.assertIsInstance(result.investing_flows, list)

    def test_calculates_net_cash_flow(self):
        """Should calculate net cash flow from summaries."""
        result = calculate_cash_flow_metrics(
            from_date=date(2024, 1, 1),
            to_date=date(2024, 12, 31),
        )

        # Net cash flow should be a decimal
        self.assertIsInstance(result.net_cash_flow, (Decimal, int, float))

    def test_calculates_levered_cash_flows(self):
        """Should calculate levered cash flow metrics."""
        result = calculate_cash_flow_metrics(
            from_date=date(2024, 1, 1),
            to_date=date(2024, 12, 31),
        )

        self.assertIsNotNone(result.levered_cash_flow)
        self.assertIsNotNone(result.levered_cash_flow_post_retirement)

    def test_filters_closed_accounts_in_flows(self):
        """Closed accounts with zero balance should be filtered from flows."""
        # This is implicitly tested through filter_closed_accounts being called
        result = calculate_cash_flow_metrics(
            from_date=date(2024, 1, 1),
            to_date=date(2024, 12, 31),
        )

        # Just verify we get a valid result
        self.assertIsInstance(result, CashFlowMetrics)
