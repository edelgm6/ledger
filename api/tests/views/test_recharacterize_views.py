import datetime
import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from api.models import Account, JournalEntryItem
from api.tests.testing_factories import (
    AccountFactory,
    EntityFactory,
    JournalEntryFactory,
    JournalEntryItemFactory,
    TransactionFactory,
)


class RecharacterizeViewsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="p")
        self.client.force_login(self.user)

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
        self.ally_bank = EntityFactory(name="Ally Bank")

        txn = TransactionFactory(
            description="Verizon", date=datetime.date(2025, 3, 1), is_closed=True
        )
        je = JournalEntryFactory(transaction=txn, date=txn.date)
        self.debit = JournalEntryItemFactory(
            journal_entry=je,
            account=self.checking,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal("50.00"),
        )

    def test_get_renders_page(self):
        resp = self.client.get(reverse("recharacterize"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Recharacterize")
        self.assertContains(resp, "recharacterize-main")
        # The manual builder renders with the shared typeahead-multiselect bound
        # to the account field (its <select multiple> lists the accounts).
        self.assertContains(resp, "Build manually")
        self.assertContains(resp, 'name="account"')
        self.assertContains(resp, "ta-trigger")
        self.assertContains(resp, "Ally Checking")

    @patch("api.services.recharacterize_services.gemini_services.call_gemini_conversation")
    def test_message_then_apply_flow(self, mock_call):
        mock_call.return_value = json.dumps(
            {
                "reply": "I'll set entity Ally Bank.",
                "operations": [
                    {
                        "filter": {"account": "Ally Checking", "entry_type": "debit"},
                        "action": {"type": "set_entity", "entity": "Ally Bank"},
                    }
                ],
            }
        )

        # Send a chat message -> preview rendered, operations stored in session.
        resp = self.client.post(
            reverse("recharacterize-message"), {"message": "tag ally checking debits"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "set entity")
        self.assertContains(resp, "Apply (1)")  # per-operation Apply button
        # Criteria are laid out so the user can eyeball the parsed filter.
        self.assertContains(resp, "Matching items where:")
        self.assertContains(resp, "Ally Checking")
        self.assertContains(resp, "debits only")

        # Apply operation 0 -> the item now carries the entity.
        resp = self.client.post(reverse("recharacterize-apply") + "?op=0")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Updated 1 journal entry item")
        self.debit.refresh_from_db()
        self.assertEqual(self.debit.entity, self.ally_bank)
        # The applied operation is removed from the plan; the rest remain.
        self.assertEqual(self.client.session["recharacterize"]["operations"], [])

    @patch("api.services.recharacterize_services.gemini_services.call_gemini_conversation")
    def test_apply_one_operation_leaves_the_rest(self, mock_call):
        other_entity = EntityFactory(name="Other Bank")
        mock_call.return_value = json.dumps(
            {
                "reply": "Two operations.",
                "operations": [
                    {
                        "filter": {"account": "Ally Checking", "entry_type": "debit"},
                        "action": {"type": "set_entity", "entity": "Ally Bank"},
                    },
                    {
                        "filter": {"account": "Ally Checking", "entry_type": "debit"},
                        "action": {"type": "set_entity", "entity": "Other Bank"},
                    },
                ],
            }
        )
        self.client.post(
            reverse("recharacterize-message"), {"message": "two ops"}
        )

        # Apply only operation 0; operation 1 must survive for a later apply.
        resp = self.client.post(reverse("recharacterize-apply") + "?op=0")
        self.assertEqual(resp.status_code, 200)
        self.debit.refresh_from_db()
        self.assertEqual(self.debit.entity, self.ally_bank)
        remaining = self.client.session["recharacterize"]["operations"]
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["action"]["entity"], "Other Bank")
        _ = other_entity

    def test_reset_clears_session(self):
        resp = self.client.post(reverse("recharacterize-reset"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No messages yet")

    @patch("api.services.recharacterize_services.gemini_services.call_gemini_conversation")
    def test_failed_turn_shows_error_banner_and_retry(self, mock_call):
        mock_call.side_effect = RuntimeError("429 RESOURCE_EXHAUSTED")
        resp = self.client.post(
            reverse("recharacterize-message"), {"message": "tag ally checking"}
        )
        self.assertEqual(resp.status_code, 200)
        # Typed banner + Retry affordance, and no canned assistant reply bubble.
        self.assertContains(resp, "rate limited (429)")
        self.assertContains(resp, "Retry")
        self.assertContains(resp, reverse("recharacterize-retry"))
        self.assertNotContains(resp, "chat-msg-assistant")
        # The user message is kept so Retry can re-send it.
        self.assertContains(resp, "tag ally checking")

    @patch("api.services.recharacterize_services.gemini_services.call_gemini_conversation")
    def test_failed_turn_preserves_prior_plan(self, mock_call):
        # First turn succeeds and proposes a plan.
        mock_call.return_value = json.dumps(
            {
                "reply": "Plan ready.",
                "operations": [
                    {
                        "filter": {"account": "Ally Checking", "entry_type": "debit"},
                        "action": {"type": "set_entity", "entity": "Ally Bank"},
                    }
                ],
            }
        )
        self.client.post(reverse("recharacterize-message"), {"message": "tag it"})
        # Second turn fails — the previously proposed plan must survive.
        mock_call.side_effect = RuntimeError("503 UNAVAILABLE")
        resp = self.client.post(
            reverse("recharacterize-message"), {"message": "actually..."}
        )
        self.assertContains(resp, "server busy (503)")
        self.assertContains(resp, "set entity")  # prior preview still shown
        self.assertEqual(
            len(self.client.session["recharacterize"]["operations"]), 1
        )

    @patch("api.services.recharacterize_services.gemini_services.call_gemini_conversation")
    def test_retry_after_failure_succeeds(self, mock_call):
        # A failed turn leaves the user message as the trailing entry.
        mock_call.side_effect = RuntimeError("503 UNAVAILABLE")
        self.client.post(
            reverse("recharacterize-message"), {"message": "tag ally checking debits"}
        )
        # Retry: the service now responds successfully.
        mock_call.side_effect = None
        mock_call.return_value = json.dumps(
            {
                "reply": "I'll set entity Ally Bank.",
                "operations": [
                    {
                        "filter": {"account": "Ally Checking", "entry_type": "debit"},
                        "action": {"type": "set_entity", "entity": "Ally Bank"},
                    }
                ],
            }
        )
        resp = self.client.post(reverse("recharacterize-retry"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "I&#x27;ll set entity Ally Bank.")
        self.assertContains(resp, "Apply")
        self.assertNotContains(resp, "server busy (503)")

    def test_retry_with_no_pending_message_just_renders(self):
        resp = self.client.post(reverse("recharacterize-retry"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "recharacterize-main")

    @patch("api.services.recharacterize_services.gemini_services.call_gemini_conversation")
    def test_view_only_message_shows_export_link_and_no_apply(self, mock_call):
        mock_call.return_value = json.dumps(
            {
                "reply": "Here are your Verizon debits.",
                "operations": [
                    {
                        "filter": {"account": "Ally Checking", "entry_type": "debit"},
                        "action": {"type": "view"},
                    }
                ],
            }
        )
        resp = self.client.post(
            reverse("recharacterize-message"), {"message": "show me verizon debits"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Export all")
        self.assertNotContains(resp, "Apply (")  # view-only: no Apply button

    @patch("api.services.recharacterize_services.gemini_services.call_gemini_conversation")
    def test_export_streams_csv_of_matched_items(self, mock_call):
        mock_call.return_value = json.dumps(
            {
                "reply": "Here you go.",
                "operations": [
                    {
                        "filter": {"account": "Ally Checking", "entry_type": "debit"},
                        "action": {"type": "view"},
                    }
                ],
            }
        )
        # Populate the session with a proposed plan.
        self.client.post(
            reverse("recharacterize-message"), {"message": "show me debits"}
        )

        resp = self.client.get(reverse("recharacterize-export"), {"op": "0"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("attachment", resp["Content-Disposition"])
        body = resp.content.decode()
        self.assertIn("Account Before", body)  # header row
        self.assertIn("Ally Checking", body)  # the matched item

    def test_export_with_no_session_returns_header_only_csv(self):
        resp = self.client.get(reverse("recharacterize-export"), {"op": "0"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        body = resp.content.decode().strip().splitlines()
        self.assertEqual(len(body), 1)  # header only, no data rows

    @patch("api.services.recharacterize_services.gemini_services.call_gemini_conversation")
    def test_page_endpoint_returns_paginated_fragment(self, mock_call):
        # 30 matching debits so the preview sample (25) has more to expand.
        for i in range(30):
            txn = TransactionFactory(
                description=f"Verizon {i}",
                date=datetime.date(2025, 4, 1),
                is_closed=True,
            )
            je = JournalEntryFactory(transaction=txn, date=txn.date)
            JournalEntryItemFactory(
                journal_entry=je,
                account=self.checking,
                type=JournalEntryItem.JournalEntryType.DEBIT,
                amount=Decimal("10.00"),
            )
        mock_call.return_value = json.dumps(
            {
                "reply": "Here are your debits.",
                "operations": [
                    {
                        "filter": {"account": "Ally Checking", "entry_type": "debit"},
                        "action": {"type": "view"},
                    }
                ],
            }
        )
        resp = self.client.post(
            reverse("recharacterize-message"), {"message": "show debits"}
        )
        # With >1 page the preview shows the pager inline (no "View all" gate).
        self.assertContains(resp, "Page 1 of")
        self.assertContains(resp, "Next")
        self.assertContains(resp, reverse("recharacterize-page"))

        # Page 1 fragment paginates with a Next control.
        resp = self.client.get(
            reverse("recharacterize-page"), {"op": "0", "page": "1"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "affected-region-0")
        self.assertContains(resp, "Page 1 of")
        self.assertContains(resp, "Next")

    def test_page_endpoint_with_no_session_renders_empty(self):
        resp = self.client.get(
            reverse("recharacterize-page"), {"op": "0", "page": "1"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No items to show")

    def test_history_panel_lists_applied_change_with_revert(self):
        from api.services.recharacterize_services import apply_operation

        ops = [
            {
                "filter": {"account": "Ally Checking", "entry_type": "debit"},
                "action": {"type": "set_entity", "entity": "Ally Bank"},
            }
        ]
        self.assertTrue(apply_operation(ops, 0).success)

        resp = self.client.get(reverse("recharacterize"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Recent changes")
        self.assertContains(resp, "Revert")

    def test_revert_endpoint_restores_and_marks_reverted(self):
        from api.models import RecharacterizeChange
        from api.services.recharacterize_services import apply_operation

        ops = [
            {
                "filter": {"account": "Ally Checking", "entry_type": "debit"},
                "action": {"type": "set_entity", "entity": "Ally Bank"},
            }
        ]
        result = apply_operation(ops, 0)
        self.debit.refresh_from_db()
        self.assertEqual(self.debit.entity, self.ally_bank)

        resp = self.client.post(
            reverse("recharacterize-revert") + f"?change={result.change_id}"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Reverted:")

        self.debit.refresh_from_db()
        self.assertIsNone(self.debit.entity)
        change = RecharacterizeChange.objects.get(id=result.change_id)
        self.assertTrue(change.is_reverted)

    def test_revert_invalid_change_reports_error(self):
        resp = self.client.post(reverse("recharacterize-revert") + "?change=999999")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "no longer exists")

    # --- manual builder (no LLM) -------------------------------------------

    def test_manual_appends_op_and_opens_manual_tab(self):
        # No Gemini mock: the manual path must not touch the model at all. The
        # account multi-select submits account PKs (typeahead-multiselect).
        resp = self.client.post(
            reverse("recharacterize-manual"),
            {
                "action_type": "set_entity",
                "account": self.checking.id,
                "entry_type": "debit",
                "target_entity": "Ally Bank",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "set entity")
        self.assertContains(resp, "Apply (1)")
        # The swap keeps the user on the Manual tab.
        self.assertContains(resp, "mode: 'manual'")
        ops = self.client.session["recharacterize"]["operations"]
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["filter"]["account"], ["Ally Checking"])
        self.assertEqual(ops[0]["action"], {"type": "set_entity", "entity": "Ally Bank"})

    def test_manual_then_apply_updates_items_and_records_history(self):
        from api.models import RecharacterizeChange

        self.client.post(
            reverse("recharacterize-manual"),
            {
                "action_type": "set_entity",
                "account": self.checking.id,
                "entry_type": "debit",
                "target_entity": "Ally Bank",
            },
        )
        resp = self.client.post(reverse("recharacterize-apply") + "?op=0")
        self.assertEqual(resp.status_code, 200)
        self.debit.refresh_from_db()
        self.assertEqual(self.debit.entity, self.ally_bank)
        # A manually applied op is revertible, same as an agent-applied one.
        self.assertTrue(RecharacterizeChange.objects.exists())

    def test_manual_invalid_date_shows_error_and_adds_no_op(self):
        resp = self.client.post(
            reverse("recharacterize-manual"),
            {
                "action_type": "clear_entity",
                "account": self.checking.id,
                "date_from": "not-a-date",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "date_from")
        self.assertContains(resp, "mode: 'manual'")
        # The invalid submit never writes the plan, so no op is added.
        state = self.client.session.get("recharacterize", {"operations": []})
        self.assertEqual(state["operations"], [])

    def test_manual_empty_filter_shows_blocked_op_in_preview(self):
        # A no-criteria op is valid form input but blocked by the guardrails,
        # surfaced inline exactly like a bad agent op — not a hard error.
        resp = self.client.post(
            reverse("recharacterize-manual"), {"action_type": "clear_entity"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "no criteria")
        self.assertEqual(
            len(self.client.session["recharacterize"]["operations"]), 1
        )
