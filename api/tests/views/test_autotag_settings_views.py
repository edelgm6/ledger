"""Tests for the Autotags Settings section HTMX views."""

from django.urls import reverse

from api.models import AutoTag, Transaction
from api.tests.test_helpers import HTMXViewTestCase
from api.tests.testing_factories import (
    AccountFactory,
    AutoTagFactory,
)


class AutoTagSettingsViewTest(HTMXViewTestCase):
    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("settings-autotags"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_panel_loads_and_lists_autotags(self):
        AutoTagFactory(search_string="listedtag")

        response = self.client.get(reverse("settings-autotags"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "listedtag")
        self.assertContains(response, "Auto Tags")
        # The re-apply button reuses the existing trigger endpoint.
        self.assertContains(response, reverse("trigger-autotag"))

    def test_new_autotag_form_view(self):
        response = self.client.get(reverse("settings-autotag-new-form"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New auto tag")
        # No Delete button on a blank create form.
        self.assertNotContains(response, 'value="delete"')

    def test_autotag_form_view_loads_autotag(self):
        autotag = AutoTagFactory(search_string="editable")
        response = self.client.get(
            reverse("settings-autotag-form", args=[autotag.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "editable")
        self.assertContains(response, 'value="delete"')

    def test_create_autotag(self):
        account = AccountFactory(is_closed=False)
        data = {
            "action": "save",
            "search_string": "amazon",
            "account": str(account.id),
            "transaction_type": Transaction.TransactionType.PURCHASE,
            "prefill": "",
            "entity": "",
        }
        response = self.client.post(reverse("settings-autotags"), data=data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(AutoTag.objects.filter(search_string="amazon").exists())
        self.assertContains(response, "Auto tag created.")

    def test_update_autotag(self):
        account = AccountFactory(is_closed=False)
        autotag = AutoTagFactory(search_string="before", account=account)
        data = {
            "action": "save",
            "search_string": "after",
            "account": str(autotag.account_id),
            "transaction_type": Transaction.TransactionType.INCOME,
            "prefill": "",
            "entity": "",
        }
        response = self.client.post(
            reverse("settings-autotag", args=[autotag.id]), data=data
        )
        self.assertEqual(response.status_code, 200)
        autotag.refresh_from_db()
        self.assertEqual(autotag.search_string, "after")
        self.assertContains(response, "Auto tag updated.")

    def test_delete_autotag(self):
        autotag = AutoTagFactory()
        response = self.client.post(
            reverse("settings-autotag", args=[autotag.id]),
            data={"action": "delete"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AutoTag.objects.filter(pk=autotag.id).exists())
        self.assertContains(response, "Auto tag deleted.")

    def test_create_without_search_string_shows_form_error(self):
        data = {
            "action": "save",
            "search_string": "",
            "account": "",
            "transaction_type": "",
            "prefill": "",
            "entity": "",
        }
        response = self.client.post(reverse("settings-autotags"), data=data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AutoTag.objects.count(), 0)
        self.assertContains(response, "This field is required")
