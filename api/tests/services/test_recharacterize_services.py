import datetime
import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from api.models import (
    Account,
    JournalEntryItem,
    RecharacterizeChange,
    RecharacterizeChangeItem,
)
from api.services import recharacterize_services
from api.services.recharacterize_services import (
    SAMPLE_LIMIT,
    apply_operation,
    build_export_rows,
    build_page,
    list_recent_changes,
    preview_plan,
    revert_change,
    run_turn,
)
from api.tests.testing_factories import (
    AccountFactory,
    EntityFactory,
    JournalEntryFactory,
    JournalEntryItemFactory,
    TransactionFactory,
)


def make_entry(
    description,
    date,
    debit_account,
    credit_account,
    amount=Decimal("50.00"),
    debit_entity=None,
    credit_entity=None,
):
    """Builds a balanced two-item journal entry and returns (debit, credit)."""
    txn = TransactionFactory(description=description, date=date, is_closed=True)
    je = JournalEntryFactory(transaction=txn, date=date, description=description)
    debit = JournalEntryItemFactory(
        journal_entry=je,
        account=debit_account,
        type=JournalEntryItem.JournalEntryType.DEBIT,
        amount=amount,
        entity=debit_entity,
    )
    credit = JournalEntryItemFactory(
        journal_entry=je,
        account=credit_account,
        type=JournalEntryItem.JournalEntryType.CREDIT,
        amount=amount,
        entity=credit_entity,
    )
    return debit, credit


class RecharacterizeServicesTest(TestCase):
    def setUp(self):
        self.checking = AccountFactory(
            name="Ally Checking",
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
            is_closed=False,
        )
        self.groceries = AccountFactory(
            name="Groceries",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.OPERATING,
            is_closed=False,
        )
        self.dining = AccountFactory(
            name="Dining",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.OPERATING,
            is_closed=False,
        )
        self.interest = AccountFactory(
            name="Interest Expense",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.INTEREST,
            is_closed=False,
        )
        self.starting_equity = AccountFactory(
            name="Starting Equity",
            type=Account.Type.EQUITY,
            special_type=Account.SpecialType.STARTING_EQUITY,
            is_closed=False,
        )
        self.ally_bank = EntityFactory(name="Ally Bank")

        # Two 2025 "Verizon" entries with a debit on Ally Checking.
        self.d1, _ = make_entry(
            "Verizon Wireless", datetime.date(2025, 3, 1), self.checking, self.groceries
        )
        self.d2, _ = make_entry(
            "Verizon Fios", datetime.date(2025, 6, 1), self.checking, self.groceries
        )
        # A 2024 Verizon entry that must NOT match the 2025 filter.
        self.d_old, _ = make_entry(
            "Verizon Wireless", datetime.date(2024, 6, 1), self.checking, self.groceries
        )

    def _verizon_2025_checking_debit_filter(self):
        return {
            "description_contains": "Verizon",
            "date_from": "2025-01-01",
            "date_to": "2025-12-31",
            "account": "Ally Checking",
            "entry_type": "debit",
        }

    # --- entity actions -----------------------------------------------------

    def test_set_entity_updates_exactly_matched_items(self):
        ops = [
            {
                "filter": self._verizon_2025_checking_debit_filter(),
                "action": {"type": "set_entity", "entity": "Ally Bank"},
            }
        ]
        preview = preview_plan(ops)
        self.assertTrue(preview.operations[0].mutates)
        self.assertEqual(preview.operations[0].affected_count, 2)

        result = apply_operation(ops, 0)
        self.assertTrue(result.success)
        self.assertEqual(result.updated_count, 2)

        self.d1.refresh_from_db()
        self.d2.refresh_from_db()
        self.d_old.refresh_from_db()
        self.assertEqual(self.d1.entity, self.ally_bank)
        self.assertEqual(self.d2.entity, self.ally_bank)
        self.assertIsNone(self.d_old.entity)  # 2024 untouched

    def test_clear_entity(self):
        self.d1.entity = self.ally_bank
        self.d1.save()
        ops = [
            {
                "filter": {"account": "Ally Checking", "entity": "Ally Bank"},
                "action": {"type": "clear_entity"},
            }
        ]
        result = apply_operation(ops, 0)
        self.assertTrue(result.success)
        self.assertEqual(result.updated_count, 1)
        self.d1.refresh_from_db()
        self.assertIsNone(self.d1.entity)

    def test_entity_only_run_leaves_balances_unchanged(self):
        start = datetime.date(2024, 1, 1)
        end = datetime.date(2025, 12, 31)
        before = self.groceries.get_balance(end, start)
        ops = [
            {
                "filter": {"description_contains": "Verizon", "account": "Groceries"},
                "action": {"type": "set_entity", "entity": "Ally Bank"},
            }
        ]
        self.assertTrue(apply_operation(ops, 0).success)
        after = self.groceries.get_balance(end, start)
        self.assertEqual(before, after)

    # --- account swaps ------------------------------------------------------

    def test_account_swap_same_type_subtype_works(self):
        ops = [
            {
                "filter": {"description_contains": "Verizon", "account": "Groceries"},
                "action": {"type": "change_account", "to_account": "Dining"},
            }
        ]
        preview = preview_plan(ops)
        self.assertTrue(preview.operations[0].mutates)
        result = apply_operation(ops, 0)
        self.assertTrue(result.success)
        self.assertEqual(result.updated_count, 3)  # all 3 Verizon grocery debits
        self.assertFalse(
            JournalEntryItem.objects.filter(account=self.groceries).exists()
        )

    def test_account_swap_different_type_blocked(self):
        ops = [
            {
                "filter": {"account": "Groceries"},
                "action": {"type": "change_account", "to_account": "Ally Checking"},
            }
        ]
        preview = preview_plan(ops)
        self.assertTrue(preview.operations[0].blocked)
        self.assertTrue(preview.operations[0].blocked)
        self.assertFalse(apply_operation(ops, 0).success)

    def test_account_swap_different_subtype_blocked(self):
        ops = [
            {
                "filter": {"account": "Groceries"},
                "action": {"type": "change_account", "to_account": "Interest Expense"},
            }
        ]
        preview = preview_plan(ops)
        self.assertTrue(preview.operations[0].blocked)
        self.assertFalse(apply_operation(ops, 0).success)

    def test_change_account_requires_source(self):
        ops = [
            {
                "filter": {"description_contains": "Verizon"},
                "action": {"type": "change_account", "to_account": "Dining"},
            }
        ]
        self.assertTrue(preview_plan(ops).operations[0].blocked)

    # --- protected accounts -------------------------------------------------

    def test_protected_account_swap_blocked(self):
        unrealized = AccountFactory(
            name="Unrealized Gains",
            type=Account.Type.INCOME,
            sub_type=Account.SubType.UNREALIZED_INVESTMENT_GAINS,
            special_type=Account.SpecialType.UNREALIZED_GAINS_AND_LOSSES,
            is_closed=False,
        )
        ops = [
            {
                "filter": {"account": "Unrealized Gains"},
                "action": {"type": "change_account", "to_account": "Groceries"},
            }
        ]
        self.assertTrue(preview_plan(ops).operations[0].blocked)
        self.assertFalse(apply_operation(ops, 0).success)
        _ = unrealized

    def test_set_entity_includes_swap_blocked_items(self):
        retained = AccountFactory(
            name="Retained Earnings",
            type=Account.Type.EQUITY,
            sub_type=Account.SubType.RETAINED_EARNINGS,
            is_closed=False,
        )
        # A swap-blocked item and a normal item, both untagged, both in 2025.
        blocked_debit, _ = make_entry(
            "Year close", datetime.date(2025, 1, 1), retained, self.checking
        )
        normal_debit, _ = make_entry(
            "Office", datetime.date(2025, 1, 2), self.dining, self.checking
        )
        ops = [
            {
                "filter": {
                    "entity_is_empty": True,
                    "date_from": "2025-01-01",
                    "date_to": "2025-12-31",
                },
                "action": {"type": "set_entity", "entity": "Ally Bank"},
            }
        ]
        # Entity tagging is allowed on every account, including swap-blocked ones.
        preview = preview_plan(ops)
        self.assertFalse(preview.operations[0].blocked)
        result = apply_operation(ops, 0)
        self.assertTrue(result.success)

        blocked_debit.refresh_from_db()
        normal_debit.refresh_from_db()
        self.assertEqual(blocked_debit.entity, self.ally_bank)  # now included
        self.assertEqual(normal_debit.entity, self.ally_bank)

    def test_starting_equity_swap_blocked(self):
        other_equity = AccountFactory(
            name="Other Equity",
            type=Account.Type.EQUITY,
            is_closed=False,
        )
        # Blocked as the swap source.
        from_ops = [
            {
                "filter": {"account": "Starting Equity"},
                "action": {"type": "change_account", "to_account": "Other Equity"},
            }
        ]
        self.assertTrue(preview_plan(from_ops).operations[0].blocked)
        self.assertFalse(apply_operation(from_ops, 0).success)
        # Blocked as the swap destination.
        to_ops = [
            {
                "filter": {"account": "Other Equity"},
                "action": {"type": "change_account", "to_account": "Starting Equity"},
            }
        ]
        self.assertTrue(preview_plan(to_ops).operations[0].blocked)
        self.assertFalse(apply_operation(to_ops, 0).success)
        _ = other_equity

    def test_set_entity_on_starting_equity_allowed(self):
        debit, _ = make_entry(
            "Opening balance",
            datetime.date(2025, 1, 1),
            self.starting_equity,
            self.checking,
        )
        ops = [
            {
                "filter": {"account": "Starting Equity"},
                "action": {"type": "set_entity", "entity": "Ally Bank"},
            }
        ]
        self.assertFalse(preview_plan(ops).operations[0].blocked)
        self.assertTrue(apply_operation(ops, 0).success)
        debit.refresh_from_db()
        self.assertEqual(debit.entity, self.ally_bank)

    # --- resolution / safety ------------------------------------------------

    def test_unresolved_entity_name_blocked(self):
        ops = [
            {
                "filter": {"account": "Ally Checking"},
                "action": {"type": "set_entity", "entity": "Nonexistent Bank"},
            }
        ]
        self.assertTrue(preview_plan(ops).operations[0].blocked)
        self.assertFalse(apply_operation(ops, 0).success)

    def test_account_name_with_whitespace_resolves(self):
        # The LLM is told to copy names verbatim but sometimes adds stray
        # whitespace; a leading/trailing space must still resolve.
        ops = [
            {
                "filter": {"account": "  Groceries  "},
                "action": {"type": "set_entity", "entity": "Ally Bank"},
            }
        ]
        self.assertFalse(preview_plan(ops).operations[0].blocked)

    def test_account_name_case_insensitive_resolves(self):
        ops = [
            {
                "filter": {"account": "groceries"},
                "action": {"type": "set_entity", "entity": "ally bank"},
            }
        ]
        self.assertFalse(preview_plan(ops).operations[0].blocked)

    def test_empty_filter_blocked(self):
        ops = [
            {"filter": {}, "action": {"type": "set_entity", "entity": "Ally Bank"}}
        ]
        self.assertTrue(preview_plan(ops).operations[0].blocked)

    def test_entity_is_empty_filter_targets_untagged_items(self):
        misc = AccountFactory(
            name="Misc",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.OPERATING,
            is_closed=False,
        )
        other_entity = EntityFactory(name="Other Bank")
        untagged, _ = make_entry(
            "Untagged", datetime.date(2025, 2, 1), misc, self.checking
        )
        tagged, _ = make_entry(
            "Tagged",
            datetime.date(2025, 2, 1),
            misc,
            self.checking,
            debit_entity=other_entity,
        )
        ops = [
            {
                "filter": {"account": "Misc", "entity_is_empty": True},
                "action": {"type": "set_entity", "entity": "Ally Bank"},
            }
        ]
        preview = preview_plan(ops)
        self.assertFalse(preview.operations[0].blocked)  # "no entity" is a valid criterion
        self.assertTrue(preview.operations[0].mutates)

        result = apply_operation(ops, 0)
        self.assertTrue(result.success)
        self.assertEqual(result.updated_count, 1)  # only the untagged Misc debit
        untagged.refresh_from_db()
        tagged.refresh_from_db()
        self.assertEqual(untagged.entity, self.ally_bank)
        self.assertEqual(tagged.entity, other_entity)  # already tagged, untouched

    # --- view-only operations -----------------------------------------------

    def test_view_op_previews_without_changes_and_hides_apply(self):
        ops = [
            {
                "filter": self._verizon_2025_checking_debit_filter(),
                "action": {"type": "view"},
            }
        ]
        preview = preview_plan(ops)
        op = preview.operations[0]
        self.assertFalse(op.blocked)
        # A view-only op never carries an Apply button: it matches items but
        # mutates nothing.
        self.assertFalse(op.mutates)
        self.assertEqual(op.affected_count, 2)
        # Preview page rows show no before/after diff.
        for row in op.page.rows:
            self.assertEqual(row["account_before"], row["account_after"])
            self.assertEqual(row["entity_before"], row["entity_after"])

    def test_view_op_cannot_be_applied(self):
        ops = [
            {
                "filter": self._verizon_2025_checking_debit_filter(),
                "action": {"type": "view"},
            }
        ]
        result = apply_operation(ops, 0)
        self.assertFalse(result.success)  # a view-only op has nothing to commit
        self.assertEqual(result.updated_count, 0)
        self.d1.refresh_from_db()
        self.assertIsNone(self.d1.entity)

    def test_mixed_view_and_mutation_counts_only_changes(self):
        ops = [
            {
                "filter": self._verizon_2025_checking_debit_filter(),
                "action": {"type": "view"},
            },
            {
                "filter": {"description_contains": "Verizon", "account": "Groceries"},
                "action": {"type": "set_entity", "entity": "Ally Bank"},
            },
        ]
        preview = preview_plan(ops)
        self.assertFalse(preview.operations[0].mutates)
        self.assertTrue(preview.operations[1].mutates)
        # Only the mutating op's 3 grocery debits will change.
        self.assertEqual(preview.operations[1].affected_count, 3)

        # The view op (index 0) has nothing to commit; the mutating op (index 1)
        # applies on its own.
        self.assertFalse(apply_operation(ops, 0).success)
        result = apply_operation(ops, 1)
        self.assertTrue(result.success)
        self.assertEqual(result.updated_count, 3)

    # --- CSV export ---------------------------------------------------------

    def test_export_returns_all_rows_beyond_sample_limit(self):
        export_acct = AccountFactory(
            name="Export Test",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.OPERATING,
            is_closed=False,
        )
        total = SAMPLE_LIMIT + 3
        for i in range(total):
            make_entry(
                "Bulk export",
                datetime.date(2025, 7, 1),
                export_acct,
                self.checking,
            )
        ops = [
            {
                "filter": {"account": "Export Test"},
                "action": {"type": "view"},
            }
        ]
        rows = build_export_rows(ops, 0)
        self.assertEqual(len(rows), total)  # full universe, not just SAMPLE_LIMIT
        first = rows[0]
        self.assertIn("account_before", first)
        self.assertIn("entity_after", first)

    def test_export_reflects_proposed_changes(self):
        ops = [
            {
                "filter": {"description_contains": "Verizon", "account": "Groceries"},
                "action": {"type": "change_account", "to_account": "Dining"},
            }
        ]
        rows = build_export_rows(ops, 0)
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row["account_before"], "Groceries")
            self.assertEqual(row["account_after"], "Dining")

    # --- inline pagination --------------------------------------------------

    def _make_bulk_view_ops(self, total):
        export_acct = AccountFactory(
            name="Paged Test",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.OPERATING,
            is_closed=False,
        )
        for _ in range(total):
            make_entry(
                "Bulk paged",
                datetime.date(2025, 7, 1),
                export_acct,
                self.checking,
            )
        return [{"filter": {"account": "Paged Test"}, "action": {"type": "view"}}]

    def test_build_page_first_page_and_metadata(self):
        total = SAMPLE_LIMIT + 3
        ops = self._make_bulk_view_ops(total)
        page = build_page(ops, 0, 1)
        self.assertEqual(len(page.rows), SAMPLE_LIMIT)
        self.assertEqual(page.total, total)
        self.assertEqual(page.num_pages, 2)
        self.assertEqual(page.page, 1)
        self.assertFalse(page.has_previous)
        self.assertTrue(page.has_next)

    def test_build_page_last_page_has_remainder(self):
        total = SAMPLE_LIMIT + 3
        ops = self._make_bulk_view_ops(total)
        page = build_page(ops, 0, 2)
        self.assertEqual(len(page.rows), 3)
        self.assertTrue(page.has_previous)
        self.assertFalse(page.has_next)

    def test_build_page_clamps_out_of_range_page(self):
        ops = self._make_bulk_view_ops(SAMPLE_LIMIT + 3)
        page = build_page(ops, 0, 99)
        self.assertIsNotNone(page)
        self.assertEqual(page.page, page.num_pages)  # clamped to last page

    def test_build_page_none_for_blocked_or_out_of_range_op(self):
        blocked_ops = [
            {
                "filter": {"account": "Ally Checking"},
                "action": {"type": "set_entity", "entity": "Nonexistent Bank"},
            }
        ]
        self.assertIsNone(build_page(blocked_ops, 0, 1))
        self.assertIsNone(build_page(blocked_ops, 5, 1))
        self.assertIsNone(build_page([], 0, 1))

    def test_build_page_reflects_proposed_changes(self):
        ops = [
            {
                "filter": {"description_contains": "Verizon", "account": "Groceries"},
                "action": {"type": "change_account", "to_account": "Dining"},
            }
        ]
        page = build_page(ops, 0, 1)
        self.assertTrue(page.rows)
        for row in page.rows:
            self.assertEqual(row["account_before"], "Groceries")
            self.assertEqual(row["account_after"], "Dining")

    def test_export_empty_for_blocked_or_out_of_range(self):
        blocked_ops = [
            {
                "filter": {"account": "Ally Checking"},
                "action": {"type": "set_entity", "entity": "Nonexistent Bank"},
            }
        ]
        self.assertEqual(build_export_rows(blocked_ops, 0), [])
        self.assertEqual(build_export_rows(blocked_ops, 5), [])
        self.assertEqual(build_export_rows([], 0), [])

    # --- turn orchestration (model mocked) ----------------------------------

    @patch("api.services.recharacterize_services.gemini_services.call_gemini_conversation")
    def test_run_turn_parses_reply_and_operations(self, mock_call):
        mock_call.return_value = json.dumps(
            {
                "reply": "Sure, here's the plan.",
                "operations": [
                    {
                        "filter": {"account": "Ally Checking"},
                        "action": {"type": "set_entity", "entity": "Ally Bank"},
                    }
                ],
            }
        )
        turn = run_turn([{"role": "user", "text": "tag ally checking"}])
        self.assertEqual(turn.reply, "Sure, here's the plan.")
        self.assertEqual(len(turn.operations), 1)
        self.assertIsNone(turn.error)
        self.assertFalse(turn.failed)

    @patch("api.services.recharacterize_services.gemini_services.call_gemini_conversation")
    def test_run_turn_degrades_on_model_error(self, mock_call):
        mock_call.side_effect = RuntimeError("503 UNAVAILABLE")
        turn = run_turn([{"role": "user", "text": "hi"}])
        self.assertEqual(turn.operations, [])
        self.assertEqual(turn.reply, "")
        self.assertTrue(turn.failed)
        self.assertIn("503", turn.error)

    def test_apply_one_at_a_time_good_op_commits_blocked_sibling_does_not(self):
        ops = [
            {
                "filter": self._verizon_2025_checking_debit_filter(),
                "action": {"type": "set_entity", "entity": "Ally Bank"},
            },
            {
                "filter": {"account": "Ally Checking"},
                "action": {"type": "set_entity", "entity": "Nonexistent Bank"},
            },
        ]
        # The good op (index 0) applies on its own.
        result = apply_operation(ops, 0)
        self.assertTrue(result.success)
        self.d1.refresh_from_db()
        self.d2.refresh_from_db()
        self.assertEqual(self.d1.entity, self.ally_bank)
        self.assertEqual(self.d2.entity, self.ally_bank)

        # The blocked sibling (index 1) fails and writes nothing.
        blocked = apply_operation(ops, 1)
        self.assertFalse(blocked.success)
        self.assertIn("blocked", blocked.error.lower())

    def test_apply_out_of_range_index_is_noop(self):
        ops = [
            {
                "filter": self._verizon_2025_checking_debit_filter(),
                "action": {"type": "set_entity", "entity": "Ally Bank"},
            }
        ]
        self.assertFalse(apply_operation(ops, 5).success)
        self.assertFalse(apply_operation(ops, -1).success)


class RecharacterizeRevertTest(TestCase):
    """Capture-on-apply, revert, conflict/missing handling, and retention."""

    def setUp(self):
        self.checking = AccountFactory(
            name="Ally Checking",
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
            is_closed=False,
        )
        self.groceries = AccountFactory(
            name="Groceries",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.OPERATING,
            is_closed=False,
        )
        self.dining = AccountFactory(
            name="Dining",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.OPERATING,
            is_closed=False,
        )
        self.ally_bank = EntityFactory(name="Ally Bank")
        self.chase = EntityFactory(name="Chase")

        # Two grocery debits, one already tagged to a different entity so we can
        # confirm revert restores each item's own prior value (not a constant).
        self.d1, _ = make_entry(
            "Verizon Wireless", datetime.date(2025, 3, 1), self.groceries, self.checking
        )
        self.d2, _ = make_entry(
            "Verizon Fios",
            datetime.date(2025, 6, 1),
            self.groceries,
            self.checking,
            debit_entity=self.chase,
        )

    def _set_entity_op(self):
        return [
            {
                "filter": {"description_contains": "Verizon", "account": "Groceries"},
                "action": {"type": "set_entity", "entity": "Ally Bank"},
            }
        ]

    def _swap_op(self):
        return [
            {
                "filter": {"description_contains": "Verizon", "account": "Groceries"},
                "action": {"type": "change_account", "to_account": "Dining"},
            }
        ]

    # --- capture ------------------------------------------------------------

    def test_apply_records_change_with_per_item_prior_values(self):
        result = apply_operation(self._set_entity_op(), 0)
        self.assertTrue(result.success)
        self.assertIsNotNone(result.change_id)

        change = RecharacterizeChange.objects.get(id=result.change_id)
        self.assertEqual(change.action_kind, "set_entity")
        self.assertEqual(change.updated_count, 2)
        self.assertEqual(change.new_entity, self.ally_bank)
        self.assertFalse(change.is_reverted)

        items = {ci.journal_entry_item_id: ci for ci in change.items.all()}
        self.assertEqual(len(items), 2)
        # d1 had no entity; d2 was tagged Chase — each prior value is captured.
        self.assertIsNone(items[self.d1.id].prior_entity_id)
        self.assertEqual(items[self.d2.id].prior_entity_id, self.chase.id)

    # --- revert -------------------------------------------------------------

    def test_revert_restores_entities_to_prior_values(self):
        result = apply_operation(self._set_entity_op(), 0)
        self.d1.refresh_from_db()
        self.d2.refresh_from_db()
        self.assertEqual(self.d1.entity, self.ally_bank)
        self.assertEqual(self.d2.entity, self.ally_bank)

        revert = revert_change(result.change_id)
        self.assertTrue(revert.success)
        self.assertEqual(revert.reverted_count, 2)
        self.assertEqual(revert.conflict_count, 0)

        self.d1.refresh_from_db()
        self.d2.refresh_from_db()
        self.assertIsNone(self.d1.entity)  # restored to no-entity
        self.assertEqual(self.d2.entity, self.chase)  # restored to Chase

        change = RecharacterizeChange.objects.get(id=result.change_id)
        self.assertTrue(change.is_reverted)
        self.assertIsNotNone(change.reverted_at)

    def test_revert_account_swap_restores_account(self):
        result = apply_operation(self._swap_op(), 0)
        self.d1.refresh_from_db()
        self.assertEqual(self.d1.account, self.dining)

        revert = revert_change(result.change_id)
        self.assertTrue(revert.success)
        self.assertEqual(revert.reverted_count, 2)
        self.d1.refresh_from_db()
        self.assertEqual(self.d1.account, self.groceries)

    def test_revert_skips_items_changed_since(self):
        first = apply_operation(self._set_entity_op(), 0)
        # A later op re-tags d1/d2 to Chase, so the first change no longer owns them.
        second_op = [
            {
                "filter": {"description_contains": "Verizon", "account": "Groceries"},
                "action": {"type": "set_entity", "entity": "Chase"},
            }
        ]
        self.assertTrue(apply_operation(second_op, 0).success)

        revert = revert_change(first.change_id)
        self.assertTrue(revert.success)
        self.assertEqual(revert.reverted_count, 0)
        self.assertEqual(revert.conflict_count, 2)

        # The later change's values survive — nothing was clobbered.
        self.d1.refresh_from_db()
        self.d2.refresh_from_db()
        self.assertEqual(self.d1.entity, self.chase)
        self.assertEqual(self.d2.entity, self.chase)

    def test_revert_counts_deleted_items_as_missing(self):
        result = apply_operation(self._set_entity_op(), 0)
        # Delete one affected item's journal entry; SET_NULL keeps the snapshot row.
        self.d1.journal_entry.delete()

        revert = revert_change(result.change_id)
        self.assertTrue(revert.success)
        self.assertEqual(revert.missing_count, 1)
        self.assertEqual(revert.reverted_count, 1)
        self.d2.refresh_from_db()
        self.assertEqual(self.d2.entity, self.chase)

    def test_revert_already_reverted_errors(self):
        result = apply_operation(self._set_entity_op(), 0)
        self.assertTrue(revert_change(result.change_id).success)
        second = revert_change(result.change_id)
        self.assertFalse(second.success)
        self.assertIn("already", second.error.lower())

    def test_revert_missing_change_errors(self):
        self.assertFalse(revert_change(999999).success)

    # --- retention ----------------------------------------------------------

    def test_history_capped_to_recent_n(self):
        with patch.object(
            recharacterize_services, "RECHARACTERIZE_HISTORY_LIMIT", 3
        ):
            change_ids = []
            for _ in range(5):
                result = apply_operation(self._set_entity_op(), 0)
                self.assertTrue(result.success)
                change_ids.append(result.change_id)

            # Only the most recent 3 survive; their item rows too.
            self.assertEqual(RecharacterizeChange.objects.count(), 3)
            survivors = set(
                RecharacterizeChange.objects.values_list("id", flat=True)
            )
            self.assertEqual(survivors, set(change_ids[-3:]))
            # The oldest two were pruned and can no longer be reverted.
            self.assertFalse(revert_change(change_ids[0]).success)
            # Pruned changes' item snapshots are gone (cascade).
            self.assertFalse(
                RecharacterizeChangeItem.objects.filter(
                    change_id=change_ids[0]
                ).exists()
            )

    def test_list_recent_changes_orders_newest_first(self):
        first = apply_operation(self._set_entity_op(), 0)
        revert_change(first.change_id)  # so list includes a reverted row
        second = apply_operation(self._swap_op(), 0)

        recent = list_recent_changes()
        self.assertEqual(recent[0].id, second.change_id)
        self.assertEqual(recent[1].id, first.change_id)


class BuildManualOperationTest(TestCase):
    def setUp(self):
        self.checking = AccountFactory(
            name="Ally Checking",
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
            is_closed=False,
        )
        self.groceries = AccountFactory(
            name="Groceries",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.OPERATING,
            is_closed=False,
        )
        self.dining = AccountFactory(
            name="Dining",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.OPERATING,
            is_closed=False,
        )
        self.starting_equity = AccountFactory(
            name="Starting Equity",
            type=Account.Type.EQUITY,
            special_type=Account.SpecialType.STARTING_EQUITY,
            is_closed=False,
        )
        self.ally_bank = EntityFactory(name="Ally Bank")
        self.d1, _ = make_entry(
            "Verizon", datetime.date(2025, 3, 1), self.checking, self.groceries
        )

    def test_drops_empty_fields_and_serializes_dates(self):
        # account/entity arrive as model objects (multi-select); names are stored.
        op = recharacterize_services.build_manual_operation(
            {
                "description_contains": "Verizon",
                "date_from": datetime.date(2025, 1, 1),
                "date_to": None,
                "account": [self.checking],
                "entity": [],
                "entity_is_empty": False,
                "entry_type": "debit",
                "action_type": "set_entity",
                "target_entity": "Ally Bank",
            }
        )
        self.assertEqual(
            op["filter"],
            {
                "description_contains": "Verizon",
                "date_from": "2025-01-01",
                "account": ["Ally Checking"],
                "entry_type": "debit",
            },
        )
        self.assertEqual(op["action"], {"type": "set_entity", "entity": "Ally Bank"})

    def test_multiple_accounts_are_stored_as_a_name_list(self):
        op = recharacterize_services.build_manual_operation(
            {"account": [self.groceries, self.dining], "action_type": "clear_entity"}
        )
        self.assertEqual(op["filter"]["account"], ["Groceries", "Dining"])

    def test_change_account_carries_to_account(self):
        op = recharacterize_services.build_manual_operation(
            {
                "account": [self.groceries],
                "action_type": "change_account",
                "to_account": "Dining",
            }
        )
        self.assertEqual(op["action"], {"type": "change_account", "to_account": "Dining"})

    def test_clear_entity_has_no_extra_action_fields(self):
        op = recharacterize_services.build_manual_operation(
            {"account": [self.checking], "action_type": "clear_entity"}
        )
        self.assertEqual(op["action"], {"type": "clear_entity"})

    def test_round_trips_to_a_valid_preview(self):
        op = recharacterize_services.build_manual_operation(
            {
                "description_contains": "Verizon",
                "account": [self.checking],
                "entry_type": "debit",
                "action_type": "set_entity",
                "target_entity": "Ally Bank",
            }
        )
        preview = preview_plan([op])
        self.assertFalse(preview.operations[0].blocked)
        self.assertTrue(preview.operations[0].mutates)
        self.assertEqual(preview.operations[0].affected_count, 1)

    def test_multi_account_filter_matches_any(self):
        # Items on either account are matched (account__in semantics): the setUp
        # Verizon credit on Groceries plus this Lunch debit on Dining = 2.
        make_entry("Lunch", datetime.date(2025, 4, 1), self.dining, self.checking)
        op = recharacterize_services.build_manual_operation(
            {"account": [self.groceries, self.dining], "action_type": "view"}
        )
        preview = preview_plan([op])
        self.assertFalse(preview.operations[0].blocked)
        self.assertEqual(preview.operations[0].affected_count, 2)

    def test_empty_filter_round_trips_to_a_blocked_preview(self):
        # No criteria → _evaluate_operation blocks it, surfaced in the preview.
        op = recharacterize_services.build_manual_operation(
            {"action_type": "clear_entity"}
        )
        preview = preview_plan([op])
        self.assertTrue(preview.operations[0].blocked)
        self.assertIn("no criteria", preview.operations[0].error)

    def test_change_account_with_multiple_sources_is_blocked(self):
        op = recharacterize_services.build_manual_operation(
            {
                "account": [self.groceries, self.dining],
                "action_type": "change_account",
                "to_account": "Dining",
            }
        )
        preview = preview_plan([op])
        self.assertTrue(preview.operations[0].blocked)
        self.assertIn("exactly one source account", preview.operations[0].error)

    def test_swap_blocked_account_round_trips_to_a_blocked_preview(self):
        op = recharacterize_services.build_manual_operation(
            {
                "account": [self.starting_equity],
                "action_type": "change_account",
                "to_account": "Groceries",
            }
        )
        preview = preview_plan([op])
        self.assertTrue(preview.operations[0].blocked)

    def test_manual_form_catalogs_lists_names(self):
        catalogs = recharacterize_services.manual_form_catalogs()
        self.assertIn("Ally Checking", catalogs.accounts)
        self.assertIn("Ally Bank", catalogs.entities)
        self.assertIn("Starting Equity", catalogs.swap_blocked)
