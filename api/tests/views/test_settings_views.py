"""Tests for the Settings page HTMX views."""

from django.urls import reverse

from api.models import Account
from api.tests.test_helpers import HTMXViewTestCase
from api.tests.testing_factories import AccountFactory, TransactionFactory


class SettingsViewTest(HTMXViewTestCase):
    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_page_loads_and_lists_accounts(self):
        AccountFactory(name="Listed Account")
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Listed Account")
        self.assertContains(response, "Settings")

    def test_page_contains_flat_menu_sections(self):
        response = self.client.get(reverse("settings"))
        # The flat menu is client-rendered from this section list.
        self.assertContains(response, "'Entities', 'Paystubs', 'Auto Tags', 'CSV Profiles'")

    def test_new_account_form_view(self):
        response = self.client.get(reverse("settings-account-new-form"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New account")
        # No Delete button on a blank create form.
        self.assertNotContains(response, 'value="delete"')

    def test_create_equity_account(self):
        data = {
            "action": "save",
            "name": "Retained Earnings",
            "type": Account.Type.EQUITY,
            "sub_type": Account.SubType.RETAINED_EARNINGS,
            "entity": "",
            "csv_profile": "",
        }
        response = self.client.post(reverse("settings"), data=data)
        self.assertEqual(response.status_code, 200)
        account = Account.objects.get(name="Retained Earnings")
        self.assertEqual(account.type, Account.Type.EQUITY)
        self.assertEqual(account.sub_type, Account.SubType.RETAINED_EARNINGS)

    def test_account_form_view_loads_account(self):
        account = AccountFactory(name="Editable Account")
        response = self.client.get(
            reverse("settings-account-form", args=[account.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Editable Account")

    def test_create_account(self):
        data = {
            "action": "save",
            "name": "New Savings",
            "type": Account.Type.ASSET,
            "sub_type": Account.SubType.CASH,
            "entity": "",
            "csv_profile": "",
        }
        response = self.client.post(reverse("settings"), data=data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Account.objects.filter(name="New Savings").exists())
        self.assertContains(response, "Account created.")

    def test_update_account(self):
        account = AccountFactory(
            name="Before", type=Account.Type.ASSET, sub_type=Account.SubType.CASH
        )
        data = {
            "action": "save",
            "name": "After",
            "type": Account.Type.ASSET,
            "sub_type": Account.SubType.CASH,
            "entity": "",
            "csv_profile": "",
        }
        response = self.client.post(
            reverse("settings-account", args=[account.id]), data=data
        )
        self.assertEqual(response.status_code, 200)
        account.refresh_from_db()
        self.assertEqual(account.name, "After")

    def test_delete_unused_account(self):
        account = AccountFactory()
        response = self.client.post(
            reverse("settings-account", args=[account.id]),
            data={"action": "delete"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Account.objects.filter(pk=account.id).exists())

    def test_delete_protected_account_shows_message(self):
        account = AccountFactory(name="Busy Account")
        TransactionFactory(account=account)

        response = self.client.post(
            reverse("settings-account", args=[account.id]),
            data={"action": "delete"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Can&#x27;t delete")
        self.assertTrue(Account.objects.filter(pk=account.id).exists())

    def test_invalid_subtype_shows_form_errors(self):
        data = {
            "action": "save",
            "name": "Bad Account",
            "type": Account.Type.ASSET,
            "sub_type": Account.SubType.SALARY,  # income sub_type, invalid for asset
            "entity": "",
            "csv_profile": "",
        }
        response = self.client.post(reverse("settings"), data=data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Account.objects.filter(name="Bad Account").exists())
        self.assertContains(response, "not a valid sub-type")
