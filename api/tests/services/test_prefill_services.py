"""Tests for prefill_services — the Settings CRUD over Prefills and Doc Searches."""

from django.test import TestCase

from api.forms import DocSearchForm
from api.models import Account, DocSearch, JournalEntryItem, Prefill
from api.services.prefill_services import (
    DocSearchResult,
    PrefillResult,
    delete_docsearch,
    delete_prefill,
    get_docsearch_form_options,
    get_docsearches,
    get_prefills,
    save_docsearch,
    save_prefill,
)
from api.tests.testing_factories import (
    AccountFactory,
    EntityFactory,
    PrefillFactory,
)


class GetPrefillsTest(TestCase):
    """Tests for get_prefills() — the Settings list query with annotations."""

    def test_orders_open_first_then_by_name(self):
        PrefillFactory(name="Bravo", is_closed=False)
        PrefillFactory(name="Alpha", is_closed=True)
        PrefillFactory(name="Charlie", is_closed=False)

        names = [p.name for p in get_prefills()]
        self.assertEqual(names, ["Bravo", "Charlie", "Alpha"])

    def test_docsearch_count_annotation(self):
        prefill = PrefillFactory()
        DocSearch.objects.create(prefill=prefill, keyword="Gross Pay")
        DocSearch.objects.create(prefill=prefill, keyword="Net Pay")
        PrefillFactory()  # unrelated prefill with no doc searches

        by_id = {p.id: p for p in get_prefills()}
        self.assertEqual(by_id[prefill.id].docsearch_count, 2)

    def test_docsearch_count_zero_when_none(self):
        prefill = PrefillFactory()
        by_id = {p.id: p for p in get_prefills()}
        self.assertEqual(by_id[prefill.id].docsearch_count, 0)


class SavePrefillTest(TestCase):
    """Tests for save_prefill() create/update."""

    def test_creates_prefill(self):
        result = save_prefill({"name": "ADP Paystub", "is_closed": False})

        self.assertIsInstance(result, PrefillResult)
        self.assertTrue(result.success)
        self.assertEqual(result.prefill.name, "ADP Paystub")
        self.assertEqual(Prefill.objects.count(), 1)

    def test_updates_prefill(self):
        prefill = PrefillFactory(name="Old", is_closed=False)

        result = save_prefill(
            {"name": "New", "is_closed": True}, instance=prefill
        )

        self.assertTrue(result.success)
        prefill.refresh_from_db()
        self.assertEqual(prefill.name, "New")
        self.assertTrue(prefill.is_closed)


class DeletePrefillTest(TestCase):
    """Tests for delete_prefill() including the PROTECT block."""

    def test_deletes_unreferenced_prefill(self):
        prefill = PrefillFactory()

        result = delete_prefill(prefill.id)

        self.assertTrue(result.success)
        self.assertEqual(Prefill.objects.count(), 0)

    def test_not_found_returns_error(self):
        result = delete_prefill(999)

        self.assertFalse(result.success)
        self.assertEqual(result.error, "Prefill not found.")

    def test_blocks_delete_when_referenced_by_docsearch(self):
        prefill = PrefillFactory(name="Con Ed")
        DocSearch.objects.create(prefill=prefill, keyword="Amount Due")

        result = delete_prefill(prefill.id)

        self.assertFalse(result.success)
        self.assertIn("Con Ed", result.error)
        self.assertEqual(Prefill.objects.count(), 1)


class DocSearchServiceTest(TestCase):
    """Tests for the Doc Search CRUD scoped to a prefill."""

    def setUp(self):
        self.prefill = PrefillFactory()
        self.account = AccountFactory(is_closed=False)

    def test_get_docsearches_scoped_to_prefill(self):
        DocSearch.objects.create(prefill=self.prefill, keyword="A")
        other = PrefillFactory()
        DocSearch.objects.create(prefill=other, keyword="B")

        result = get_docsearches(self.prefill.id)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].keyword, "A")

    def test_save_docsearch_sets_parent_prefill_on_create(self):
        cleaned = {
            "keyword": "Gross Pay",
            "table_name": None,
            "row": None,
            "column": None,
            "account": self.account,
            "journal_entry_item_type": (
                JournalEntryItem.JournalEntryType.DEBIT
            ),
            "selection": None,
            "entity": None,
        }

        result = save_docsearch(self.prefill, cleaned)

        self.assertIsInstance(result, DocSearchResult)
        self.assertTrue(result.success)
        self.assertEqual(result.doc_search.prefill_id, self.prefill.id)
        self.assertEqual(result.doc_search.account_id, self.account.id)

    def test_save_docsearch_updates_existing(self):
        ds = DocSearch.objects.create(prefill=self.prefill, keyword="Old")
        cleaned = {
            "keyword": "New",
            "table_name": None,
            "row": None,
            "column": None,
            "account": self.account,
            "journal_entry_item_type": (
                JournalEntryItem.JournalEntryType.CREDIT
            ),
            "selection": None,
            "entity": None,
        }

        result = save_docsearch(self.prefill, cleaned, instance=ds)

        self.assertTrue(result.success)
        ds.refresh_from_db()
        self.assertEqual(ds.keyword, "New")
        self.assertEqual(DocSearch.objects.count(), 1)

    def test_delete_docsearch(self):
        ds = DocSearch.objects.create(prefill=self.prefill, keyword="A")

        result = delete_docsearch(ds.id)

        self.assertTrue(result.success)
        self.assertEqual(DocSearch.objects.count(), 0)

    def test_get_docsearch_form_options_excludes_closed_accounts(self):
        AccountFactory(is_closed=True)
        accounts, entities = get_docsearch_form_options()

        self.assertIn(self.account, accounts)
        self.assertTrue(all(not a.is_closed for a in accounts))


class DocSearchFormValidationTest(TestCase):
    """The form reuses DocSearch.clean() for the either/or field rules."""

    def setUp(self):
        self.account = AccountFactory(is_closed=False)

    def _data(self, **overrides):
        data = {
            "keyword": "",
            "table_name": "",
            "row": "",
            "column": "",
            "account": "",
            "journal_entry_item_type": "",
            "selection": "",
            "entity": "",
        }
        data.update(overrides)
        return data

    def test_valid_keyword_search_with_account(self):
        form = DocSearchForm(
            self._data(
                keyword="Gross Pay",
                account=str(self.account.id),
                journal_entry_item_type=(
                    JournalEntryItem.JournalEntryType.DEBIT
                ),
            )
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_valid_table_search_with_selection(self):
        form = DocSearchForm(
            self._data(
                table_name="Summary", row="Total", column="Amount",
                selection="Company",
            )
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_without_keyword_or_row_column(self):
        form = DocSearchForm(
            self._data(
                account=str(self.account.id),
                journal_entry_item_type=(
                    JournalEntryItem.JournalEntryType.DEBIT
                ),
            )
        )
        self.assertFalse(form.is_valid())

    def test_invalid_with_both_account_and_selection(self):
        form = DocSearchForm(
            self._data(
                keyword="Gross Pay",
                account=str(self.account.id),
                journal_entry_item_type=(
                    JournalEntryItem.JournalEntryType.DEBIT
                ),
                selection="Company",
            )
        )
        self.assertFalse(form.is_valid())
