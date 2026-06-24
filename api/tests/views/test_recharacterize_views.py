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
        self.assertContains(resp, "Apply")
        # Criteria are laid out so the user can eyeball the parsed filter.
        self.assertContains(resp, "Matching items where:")
        self.assertContains(resp, "Ally Checking")
        self.assertContains(resp, "debits only")

        # Apply -> the item now carries the entity.
        resp = self.client.post(reverse("recharacterize-apply"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Updated 1 journal entry item")
        self.debit.refresh_from_db()
        self.assertEqual(self.debit.entity, self.ally_bank)

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
