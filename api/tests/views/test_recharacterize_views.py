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
