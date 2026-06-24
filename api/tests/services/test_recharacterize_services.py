import datetime
import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from api.models import Account, JournalEntryItem
from api.services.recharacterize_services import (
    apply_plan,
    preview_plan,
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
        self.assertTrue(preview.can_apply)
        self.assertEqual(preview.total_affected, 2)

        result = apply_plan(ops)
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
        result = apply_plan(ops)
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
        self.assertTrue(apply_plan(ops).success)
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
        self.assertTrue(preview.can_apply)
        result = apply_plan(ops)
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
        self.assertTrue(preview.has_blocks)
        self.assertFalse(preview.can_apply)
        self.assertFalse(apply_plan(ops).success)

    def test_account_swap_different_subtype_blocked(self):
        ops = [
            {
                "filter": {"account": "Groceries"},
                "action": {"type": "change_account", "to_account": "Interest Expense"},
            }
        ]
        preview = preview_plan(ops)
        self.assertTrue(preview.has_blocks)
        self.assertFalse(apply_plan(ops).success)

    def test_change_account_requires_source(self):
        ops = [
            {
                "filter": {"description_contains": "Verizon"},
                "action": {"type": "change_account", "to_account": "Dining"},
            }
        ]
        self.assertTrue(preview_plan(ops).has_blocks)

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
        self.assertTrue(preview_plan(ops).has_blocks)
        self.assertFalse(apply_plan(ops).success)
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
        self.assertFalse(preview.has_blocks)
        result = apply_plan(ops)
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
        self.assertTrue(preview_plan(from_ops).has_blocks)
        self.assertFalse(apply_plan(from_ops).success)
        # Blocked as the swap destination.
        to_ops = [
            {
                "filter": {"account": "Other Equity"},
                "action": {"type": "change_account", "to_account": "Starting Equity"},
            }
        ]
        self.assertTrue(preview_plan(to_ops).has_blocks)
        self.assertFalse(apply_plan(to_ops).success)
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
        self.assertFalse(preview_plan(ops).has_blocks)
        self.assertTrue(apply_plan(ops).success)
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
        self.assertTrue(preview_plan(ops).has_blocks)
        self.assertFalse(apply_plan(ops).success)

    def test_account_name_with_whitespace_resolves(self):
        # The LLM is told to copy names verbatim but sometimes adds stray
        # whitespace; a leading/trailing space must still resolve.
        ops = [
            {
                "filter": {"account": "  Groceries  "},
                "action": {"type": "set_entity", "entity": "Ally Bank"},
            }
        ]
        self.assertFalse(preview_plan(ops).has_blocks)

    def test_account_name_case_insensitive_resolves(self):
        ops = [
            {
                "filter": {"account": "groceries"},
                "action": {"type": "set_entity", "entity": "ally bank"},
            }
        ]
        self.assertFalse(preview_plan(ops).has_blocks)

    def test_empty_filter_blocked(self):
        ops = [
            {"filter": {}, "action": {"type": "set_entity", "entity": "Ally Bank"}}
        ]
        self.assertTrue(preview_plan(ops).has_blocks)

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
        self.assertFalse(preview.has_blocks)  # "no entity" is a valid criterion
        self.assertTrue(preview.can_apply)

        result = apply_plan(ops)
        self.assertTrue(result.success)
        self.assertEqual(result.updated_count, 1)  # only the untagged Misc debit
        untagged.refresh_from_db()
        tagged.refresh_from_db()
        self.assertEqual(untagged.entity, self.ally_bank)
        self.assertEqual(tagged.entity, other_entity)  # already tagged, untouched

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

    def test_apply_is_atomic_one_bad_op_aborts_all(self):
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
        result = apply_plan(ops)
        self.assertFalse(result.success)
        # First op's items must remain unchanged (no partial write).
        self.d1.refresh_from_db()
        self.d2.refresh_from_db()
        self.assertIsNone(self.d1.entity)
        self.assertIsNone(self.d2.entity)
