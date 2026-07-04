"""Tests for autotag_services — the Settings CRUD over AutoTags."""

from django.test import TestCase

from api.models import AutoTag, Transaction
from api.services.autotag_services import (
    AutoTagResult,
    delete_autotag,
    get_autotag_form_options,
    get_autotags,
    save_autotag,
)
from api.tests.testing_factories import (
    AccountFactory,
    AutoTagFactory,
    EntityFactory,
    PrefillFactory,
)


class GetAutotagsTest(TestCase):
    """Tests for get_autotags() — the Settings list query."""

    def test_orders_by_search_string(self):
        AutoTagFactory(search_string="charlie")
        AutoTagFactory(search_string="alpha")
        AutoTagFactory(search_string="bravo")

        strings = [t.search_string for t in get_autotags()]
        self.assertEqual(strings, ["alpha", "bravo", "charlie"])


class SaveAutotagTest(TestCase):
    """Tests for save_autotag() create/update."""

    def test_creates_autotag(self):
        account = AccountFactory()
        result = save_autotag(
            {
                "search_string": "amazon",
                "account": account,
                "transaction_type": Transaction.TransactionType.PURCHASE,
                "prefill": None,
                "entity": None,
            }
        )

        self.assertIsInstance(result, AutoTagResult)
        self.assertTrue(result.success)
        self.assertEqual(result.autotag.search_string, "amazon")
        self.assertEqual(result.autotag.account_id, account.id)
        self.assertEqual(AutoTag.objects.count(), 1)

    def test_creates_autotag_with_only_search_string(self):
        result = save_autotag(
            {
                "search_string": "venmo",
                "account": None,
                "transaction_type": "",
                "prefill": None,
                "entity": None,
            }
        )

        self.assertTrue(result.success)
        self.assertIsNone(result.autotag.account)
        self.assertEqual(AutoTag.objects.count(), 1)

    def test_updates_autotag(self):
        autotag = AutoTagFactory(search_string="old")
        entity = EntityFactory()

        result = save_autotag(
            {
                "search_string": "new",
                "account": autotag.account,
                "transaction_type": Transaction.TransactionType.INCOME,
                "prefill": None,
                "entity": entity,
            },
            instance=autotag,
        )

        self.assertTrue(result.success)
        autotag.refresh_from_db()
        self.assertEqual(autotag.search_string, "new")
        self.assertEqual(autotag.entity_id, entity.id)
        self.assertEqual(AutoTag.objects.count(), 1)


class DeleteAutotagTest(TestCase):
    """Tests for delete_autotag()."""

    def test_deletes_autotag(self):
        autotag = AutoTagFactory()

        result = delete_autotag(autotag.id)

        self.assertTrue(result.success)
        self.assertEqual(AutoTag.objects.count(), 0)

    def test_not_found_returns_error(self):
        result = delete_autotag(999)

        self.assertFalse(result.success)
        self.assertEqual(result.error, "Auto tag not found.")


class GetAutotagFormOptionsTest(TestCase):
    """Tests for get_autotag_form_options() — the dropdown options."""

    def test_excludes_closed_accounts_and_prefills(self):
        open_account = AccountFactory(is_closed=False)
        AccountFactory(is_closed=True)
        open_prefill = PrefillFactory(is_closed=False)
        PrefillFactory(is_closed=True)
        entity = EntityFactory()

        accounts, prefills, entities = get_autotag_form_options()

        self.assertIn(open_account, accounts)
        self.assertTrue(all(not a.is_closed for a in accounts))
        self.assertIn(open_prefill, prefills)
        self.assertTrue(all(not p.is_closed for p in prefills))
        self.assertIn(entity, entities)
