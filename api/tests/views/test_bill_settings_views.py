"""Tests for the utility-bill Settings HTMX views."""

from unittest.mock import patch

from django.urls import reverse

from api.models import Account, Transaction, UtilityBill, UtilityBillRule
from api.tests.test_helpers import HTMXViewTestCase
from api.tests.testing_factories import AccountFactory


def make_rule(**kwargs):
    defaults = {
        "from_address": "billing@x.com",
        "subject": "Your bill",
        "account_number": "123",
        "transaction_description_match": "DOM",
        "account": AccountFactory(type=Account.Type.EXPENSE, is_closed=False),
    }
    defaults.update(kwargs)
    return UtilityBillRule.objects.create(**defaults)


class BillRulesViewTest(HTMXViewTestCase):
    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("settings-bill-rules"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_get_lists_rules(self):
        make_rule(account_number="555")
        response = self.client.get(reverse("settings-bill-rules"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "555")
        self.assertContains(response, "Bill Rules")

    def test_new_form(self):
        response = self.client.get(reverse("settings-bill-rule-new-form"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New rule")
        self.assertNotContains(response, 'value="delete"')

    def test_create_rule(self):
        account = AccountFactory(type=Account.Type.EXPENSE, is_closed=False)
        data = {
            "action": "save",
            "from_address": "billing@dom.com",
            "subject": "Bill ready",
            "account_number": "987",
            "address_hint": "",
            "transaction_description_match": "DOMINION",
            "account": account.id,
            "entity": "",
            "transaction_type": Transaction.TransactionType.PURCHASE,
        }
        response = self.client.post(reverse("settings-bill-rules"), data=data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            UtilityBillRule.objects.filter(account_number="987").exists()
        )
        self.assertContains(response, "Rule created.")

    def test_update_rule(self):
        rule = make_rule(account_number="111")
        data = {
            "action": "save",
            "from_address": rule.from_address,
            "subject": rule.subject,
            "account_number": "222",
            "address_hint": "",
            "transaction_description_match": rule.transaction_description_match,
            "account": rule.account_id,
            "entity": "",
            "transaction_type": rule.transaction_type,
        }
        response = self.client.post(
            reverse("settings-bill-rule", args=[rule.id]), data=data
        )
        self.assertEqual(response.status_code, 200)
        rule.refresh_from_db()
        self.assertEqual(rule.account_number, "222")

    def test_delete_rule(self):
        rule = make_rule()
        response = self.client.post(
            reverse("settings-bill-rule", args=[rule.id]),
            data={"action": "delete"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(UtilityBillRule.objects.filter(pk=rule.id).exists())

    def test_invalid_form_shows_errors(self):
        data = {
            "action": "save",
            "from_address": "",
            "subject": "",
            "account_number": "",
            "transaction_description_match": "",
            "account": "",
            "entity": "",
            "transaction_type": Transaction.TransactionType.PURCHASE,
        }
        response = self.client.post(reverse("settings-bill-rules"), data=data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(UtilityBillRule.objects.count(), 0)


class BillsViewTest(HTMXViewTestCase):
    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("settings-bills"))
        self.assertEqual(response.status_code, 302)

    def test_get_lists_bills(self):
        UtilityBill.objects.create(
            source_message_id="b1",
            vendor="Dominion Energy",
            status=UtilityBill.Status.PARSED,
        )
        response = self.client.get(reverse("settings-bills"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dominion Energy")
        self.assertContains(response, "Utility Bills")

    def test_failed_bill_shows_short_error_and_tooltip(self):
        UtilityBill.objects.create(
            source_message_id="f1",
            vendor="Georgia Power",
            status=UtilityBill.Status.FAILED,
            error_message="503 UNAVAILABLE: The model is overloaded.",
        )
        response = self.client.get(reverse("settings-bills"))
        self.assertEqual(response.status_code, 200)
        # Compact label inline; full error available via the title tooltip.
        self.assertContains(response, "server busy (503)")
        self.assertContains(response, "The model is overloaded.")
        self.assertContains(response, "↻ Retry")

    @patch("api.views.bill_settings_views.bill_services.poll_bill_emails")
    def test_poll_now(self, mock_poll):
        from api.services.bill_services import PollResult

        mock_poll.return_value = PollResult(fetched=2, new=1, parsed=1)
        response = self.client.post(
            reverse("settings-bills"), data={"action": "poll"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Poll complete")
        mock_poll.assert_called_once()

    @patch("api.views.bill_settings_views.bill_services.retry_bill")
    def test_retry(self, mock_retry):
        bill = UtilityBill.objects.create(
            source_message_id="b1", status=UtilityBill.Status.FAILED
        )
        returned = UtilityBill(
            source_message_id="b1", status=UtilityBill.Status.PARSED
        )
        mock_retry.return_value = returned

        response = self.client.post(
            reverse("settings-bills"),
            data={"action": "retry", "bill_id": bill.id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Retried bill")
        mock_retry.assert_called_once_with(bill.id)
