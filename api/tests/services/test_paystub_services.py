from decimal import Decimal

from django.test import TestCase

from api.models import (
    Account,
    JournalEntry,
    JournalEntryItem,
    Paystub,
    PaystubValue,
    Prefill,
    S3File,
)
from api.services.paystub_services import (
    PaystubDetailData,
    PaystubsTableData,
    get_paystub_detail_data,
    get_paystubs_table_data,
)
from api.tests.testing_factories import AccountFactory, JournalEntryFactory, PrefillFactory


class GetPaystubsTableDataTest(TestCase):
    """Tests for get_paystubs_table_data() function."""

    def setUp(self):
        self.prefill = PrefillFactory()

    def test_returns_pending_when_textract_jobs_exist(self):
        """has_pending_jobs=True when a file has not reached COMPLETE."""
        S3File.objects.create(
            prefill=self.prefill,
            url="https://example.com/pending.pdf",
            user_filename="pending.pdf",
            s3_filename="pending.pdf",
        )

        result = get_paystubs_table_data()

        self.assertIsInstance(result, PaystubsTableData)
        self.assertTrue(result.has_pending_jobs)
        self.assertEqual(result.paystubs, [])

    def test_returns_unlinked_paystubs_when_no_pending_jobs(self):
        """Returns paystubs where journal_entry is null."""
        s3file = S3File.objects.create(
            prefill=self.prefill,
            url="https://example.com/complete.pdf",
            user_filename="complete.pdf",
            s3_filename="complete.pdf",
            status=S3File.Status.COMPLETE,
        )
        paystub = Paystub.objects.create(
            document=s3file,
            page_id="page1",
            title="Test Paystub",
            journal_entry=None,
        )

        result = get_paystubs_table_data()

        self.assertIsInstance(result, PaystubsTableData)
        self.assertFalse(result.has_pending_jobs)
        self.assertEqual(len(result.paystubs), 1)
        self.assertEqual(result.paystubs[0], paystub)

    def test_returns_empty_list_when_all_paystubs_linked(self):
        """Returns empty paystubs list when all have journal entries."""
        s3file = S3File.objects.create(
            prefill=self.prefill,
            url="https://example.com/linked.pdf",
            user_filename="linked.pdf",
            s3_filename="linked.pdf",
            status=S3File.Status.COMPLETE,
        )
        journal_entry = JournalEntryFactory()
        Paystub.objects.create(
            document=s3file,
            page_id="page1",
            title="Linked Paystub",
            journal_entry=journal_entry,
        )

        result = get_paystubs_table_data()

        self.assertFalse(result.has_pending_jobs)
        self.assertEqual(result.paystubs, [])

    def test_has_active_jobs_true_when_file_processing(self):
        """has_active_jobs=True when a pending file is still PENDING/PROCESSING."""
        S3File.objects.create(
            prefill=self.prefill,
            url="https://example.com/processing.pdf",
            user_filename="processing.pdf",
            s3_filename="processing.pdf",
            status=S3File.Status.PROCESSING,
        )

        result = get_paystubs_table_data()

        self.assertTrue(result.has_pending_jobs)
        self.assertTrue(result.has_active_jobs)

    def test_has_active_jobs_false_when_only_failed(self):
        """has_active_jobs=False when all pending files are terminal (FAILED)."""
        S3File.objects.create(
            prefill=self.prefill,
            url="https://example.com/failed.pdf",
            user_filename="failed.pdf",
            s3_filename="failed.pdf",
            status=S3File.Status.FAILED,
            error_message="503 UNAVAILABLE",
        )

        result = get_paystubs_table_data()

        self.assertTrue(result.has_pending_jobs)
        self.assertFalse(result.has_active_jobs)

    def test_paystubs_ordered_by_title(self):
        """Paystubs returned in title order."""
        s3file = S3File.objects.create(
            prefill=self.prefill,
            url="https://example.com/ordered.pdf",
            user_filename="ordered.pdf",
            s3_filename="ordered.pdf",
            status=S3File.Status.COMPLETE,
        )
        paystub_b = Paystub.objects.create(
            document=s3file, page_id="page1", title="B Paystub"
        )
        paystub_a = Paystub.objects.create(
            document=s3file, page_id="page2", title="A Paystub"
        )
        paystub_c = Paystub.objects.create(
            document=s3file, page_id="page3", title="C Paystub"
        )

        result = get_paystubs_table_data()

        self.assertEqual(result.paystubs[0], paystub_a)
        self.assertEqual(result.paystubs[1], paystub_b)
        self.assertEqual(result.paystubs[2], paystub_c)


class GetPaystubDetailDataTest(TestCase):
    """Tests for get_paystub_detail_data() function."""

    def setUp(self):
        self.prefill = PrefillFactory()
        self.account = AccountFactory()
        self.s3file = S3File.objects.create(
            prefill=self.prefill,
            url="https://example.com/detail.pdf",
            user_filename="detail.pdf",
            s3_filename="detail.pdf",
            status=S3File.Status.COMPLETE,
        )
        self.paystub = Paystub.objects.create(
            document=self.s3file, page_id="page1", title="Detail Paystub"
        )

    def test_returns_paystub_values_for_id(self):
        """Returns PaystubValues associated with paystub_id."""
        PaystubValue.objects.create(
            paystub=self.paystub,
            account=self.account,
            amount=Decimal("1000.00"),
            journal_entry_item_type=JournalEntryItem.JournalEntryType.CREDIT,
        )
        PaystubValue.objects.create(
            paystub=self.paystub,
            account=self.account,
            amount=Decimal("200.00"),
            journal_entry_item_type=JournalEntryItem.JournalEntryType.DEBIT,
        )

        result = get_paystub_detail_data(self.paystub.pk)

        self.assertIsInstance(result, PaystubDetailData)
        self.assertEqual(result.paystub_id, self.paystub.pk)
        self.assertEqual(result.paystub_values.count(), 2)

    def test_includes_account_relation(self):
        """PaystubValues have account select_related."""
        PaystubValue.objects.create(
            paystub=self.paystub,
            account=self.account,
            amount=Decimal("500.00"),
            journal_entry_item_type=JournalEntryItem.JournalEntryType.DEBIT,
        )

        result = get_paystub_detail_data(self.paystub.pk)

        # Access account without additional query (would fail if not select_related)
        paystub_value = result.paystub_values.first()
        self.assertEqual(paystub_value.account, self.account)

    def test_returns_empty_queryset_for_nonexistent_paystub(self):
        """Returns empty queryset when paystub_id doesn't exist."""
        result = get_paystub_detail_data(99999)

        self.assertEqual(result.paystub_id, 99999)
        self.assertEqual(result.paystub_values.count(), 0)


class FailedFileDoesNotHidePaystubsTest(TestCase):
    """A terminal FAILED upload must not blank the paystubs table.

    `status` used to have a rival encoding of "done" in an `analysis_complete`
    timestamp, and the gate read the timestamp. A FAILED file never got one, so
    it counted as pending forever: `paystubs` came back empty and every unlinked
    paystub vanished from the journal-entry page until someone retried or
    deleted the failed upload. `has_active_jobs` was correctly False, so the
    poller had already stopped -- the page just sat there showing nothing.
    """

    def setUp(self):
        self.prefill = PrefillFactory()
        self.complete_file = S3File.objects.create(
            prefill=self.prefill,
            url="https://example.com/ok.pdf",
            user_filename="ok.pdf",
            s3_filename="ok.pdf",
            status=S3File.Status.COMPLETE,
        )
        self.paystub = Paystub.objects.create(
            document=self.complete_file,
            page_id="p1",
            title="Unlinked Paystub",
            journal_entry=None,
        )

    def _add_failed_file(self):
        return S3File.objects.create(
            prefill=self.prefill,
            url="https://example.com/failed.pdf",
            user_filename="failed.pdf",
            s3_filename="failed.pdf",
            status=S3File.Status.FAILED,
            error_message="503 UNAVAILABLE",
        )

    def test_failed_file_still_shows_unlinked_paystubs(self):
        self._add_failed_file()

        result = get_paystubs_table_data()

        self.assertEqual(
            result.paystubs,
            [self.paystub],
            "a failed upload must not hide unlinked paystubs",
        )
        self.assertFalse(result.has_active_jobs)

    def test_failed_file_is_still_listed_so_it_can_be_retried(self):
        failed = self._add_failed_file()

        result = get_paystubs_table_data()

        self.assertIn(failed, result.pending_files)
        self.assertTrue(result.has_pending_jobs)

    def test_active_job_still_hides_paystubs(self):
        """Work genuinely in flight keeps gating the list, as before."""
        S3File.objects.create(
            prefill=self.prefill,
            url="https://example.com/busy.pdf",
            user_filename="busy.pdf",
            s3_filename="busy.pdf",
            status=S3File.Status.PROCESSING,
        )

        result = get_paystubs_table_data()

        self.assertEqual(result.paystubs, [])
        self.assertTrue(result.has_active_jobs)

    def test_rendered_table_shows_both_the_failure_and_the_paystub(self):
        """End to end through the helper: the retry affordance and the paystub
        must appear together, in one root element so the HTMX outerHTML swap
        does not leave a duplicate table behind."""
        from api.views.journal_entry_helpers import render_paystubs_table

        self._add_failed_file()
        html = render_paystubs_table(get_paystubs_table_data())

        self.assertIn("Unlinked Paystub", html)
        self.assertIn("failed.pdf", html)
        self.assertIn("Retry", html)
        self.assertEqual(
            html.count('id="paystubs-table-wrapper"'),
            1,
            "the paystubs table must be rendered exactly once",
        )
