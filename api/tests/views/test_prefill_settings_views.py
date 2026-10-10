"""Tests for the Prefills Settings section HTMX views.

This section had no view tests at all, which mattered: it is the only Settings
section with two CRUD handlers (prefills, and the doc searches that hang off
them), so it was the least protected part of the most duplicated code.
"""

from django.urls import reverse

from api.models import Account, DocSearch, JournalEntryItem, Prefill
from api.tests.test_helpers import HTMXViewTestCase
from api.tests.testing_factories import (
    AccountFactory,
    EntityFactory,
    PrefillFactory,
)


class PrefillSettingsViewTest(HTMXViewTestCase):
    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("settings-prefills"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_panel_loads_and_lists_prefills(self):
        PrefillFactory(name="Paycheck Template")
        response = self.client.get(reverse("settings-prefills"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Paycheck Template")

    def test_new_prefill_form_view(self):
        response = self.client.get(reverse("settings-prefill-new-form"))
        self.assertEqual(response.status_code, 200)

    def test_edit_prefill_form_view(self):
        prefill = PrefillFactory(name="Editable")
        response = self.client.get(
            reverse("settings-prefill-form", args=[prefill.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Editable")

    def test_create_prefill(self):
        response = self.client.post(
            reverse("settings-prefills"), {"name": "Created Prefill"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Prefill.objects.filter(name="Created Prefill").exists())

    def test_update_prefill(self):
        prefill = PrefillFactory(name="Before")
        response = self.client.post(
            reverse("settings-prefill", args=[prefill.id]), {"name": "After"}
        )
        self.assertEqual(response.status_code, 200)
        prefill.refresh_from_db()
        self.assertEqual(prefill.name, "After")

    def test_create_prefill_with_invalid_data_rerenders(self):
        response = self.client.post(reverse("settings-prefills"), {"name": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Prefill.objects.filter(name="").exists())

    def test_delete_prefill(self):
        prefill = PrefillFactory(name="Doomed")
        response = self.client.post(
            reverse("settings-prefill", args=[prefill.id]), {"action": "delete"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Prefill.objects.filter(pk=prefill.pk).exists())

    def test_delete_prefill_in_use_reports_an_error(self):
        """A prefill referenced by a doc search is PROTECTed; the view must
        surface that rather than 500."""
        prefill = PrefillFactory(name="Referenced")
        account = AccountFactory(
            name="Gross Pay",
            type=Account.Type.INCOME,
            sub_type=Account.SubType.SALARY,
            # DocSearchForm's account queryset excludes closed accounts, and
            # AccountFactory randomizes is_closed.
            is_closed=False,
        )
        DocSearch.objects.create(
            prefill=prefill,
            keyword="Gross Pay",
            account=account,
            journal_entry_item_type=JournalEntryItem.JournalEntryType.CREDIT,
        )
        response = self.client.post(
            reverse("settings-prefill", args=[prefill.id]), {"action": "delete"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Prefill.objects.filter(pk=prefill.pk).exists())


class DocSearchViewTest(HTMXViewTestCase):
    def setUp(self):
        super().setUp()
        self.prefill = PrefillFactory(name="Paystub")
        self.account = AccountFactory(
            name="Gross Pay",
            type=Account.Type.INCOME,
            sub_type=Account.SubType.SALARY,
            # DocSearchForm's account queryset excludes closed accounts, and
            # AccountFactory randomizes is_closed.
            is_closed=False,
        )
        self.entity = EntityFactory(name="Employer")

    def _valid_payload(self, **overrides):
        """DocSearch.clean requires a keyword (or row+column) and an
        account+type (or a selection)."""
        payload = {
            "keyword": "Gross Pay",
            "account": str(self.account.id),
            "journal_entry_item_type": JournalEntryItem.JournalEntryType.CREDIT,
            "entity": str(self.entity.id),
        }
        payload.update(overrides)
        return payload

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(
            reverse("settings-prefill-docsearches", args=[self.prefill.id])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_panel_loads_for_its_prefill(self):
        response = self.client.get(
            reverse("settings-prefill-docsearches", args=[self.prefill.id])
        )
        self.assertEqual(response.status_code, 200)

    def test_new_docsearch_form_view(self):
        response = self.client.get(
            reverse("settings-docsearch-new-form", args=[self.prefill.id])
        )
        self.assertEqual(response.status_code, 200)

    def test_create_docsearch(self):
        response = self.client.post(
            reverse("settings-prefill-docsearches", args=[self.prefill.id]),
            self._valid_payload(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            DocSearch.objects.filter(
                prefill=self.prefill, keyword="Gross Pay"
            ).exists()
        )

    def test_created_docsearch_is_scoped_to_its_prefill(self):
        """`prefill` is excluded from the form; the view supplies it."""
        other = PrefillFactory(name="Other")
        self.client.post(
            reverse("settings-prefill-docsearches", args=[self.prefill.id]),
            self._valid_payload(),
        )
        self.assertEqual(DocSearch.objects.filter(prefill=other).count(), 0)
        self.assertEqual(DocSearch.objects.filter(prefill=self.prefill).count(), 1)

    def test_update_docsearch(self):
        doc_search = DocSearch.objects.create(
            prefill=self.prefill,
            keyword="Old Keyword",
            account=self.account,
            journal_entry_item_type=JournalEntryItem.JournalEntryType.CREDIT,
        )
        response = self.client.post(
            reverse("settings-docsearch", args=[self.prefill.id, doc_search.id]),
            self._valid_payload(keyword="New Keyword"),
        )
        self.assertEqual(response.status_code, 200)
        doc_search.refresh_from_db()
        self.assertEqual(doc_search.keyword, "New Keyword")

    def test_invalid_docsearch_rerenders_with_the_model_rule_error(self):
        """Neither keyword nor row+column -> DocSearch.clean rejects it, and
        the view must re-render rather than 500."""
        response = self.client.post(
            reverse("settings-prefill-docsearches", args=[self.prefill.id]),
            self._valid_payload(keyword=""),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DocSearch.objects.count(), 0)

    def test_delete_docsearch(self):
        doc_search = DocSearch.objects.create(
            prefill=self.prefill,
            keyword="Doomed",
            account=self.account,
            journal_entry_item_type=JournalEntryItem.JournalEntryType.CREDIT,
        )
        response = self.client.post(
            reverse("settings-docsearch", args=[self.prefill.id, doc_search.id]),
            {"action": "delete"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DocSearch.objects.filter(pk=doc_search.pk).exists())
