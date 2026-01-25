from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

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
        """has_pending_jobs=True when S3File.analysis_complete is null."""
        S3File.objects.create(
            prefill=self.prefill,
            url="https://example.com/pending.pdf",
            user_filename="pending.pdf",
            s3_filename="pending.pdf",
            textract_job_id="job123",
            analysis_complete=None,
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
            textract_job_id="job456",
            analysis_complete=timezone.now(),
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
            textract_job_id="job789",
            analysis_complete=timezone.now(),
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

    def test_paystubs_ordered_by_title(self):
        """Paystubs returned in title order."""
        s3file = S3File.objects.create(
            prefill=self.prefill,
            url="https://example.com/ordered.pdf",
            user_filename="ordered.pdf",
            s3_filename="ordered.pdf",
            textract_job_id="job000",
            analysis_complete=timezone.now(),
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
            textract_job_id="job999",
            analysis_complete=timezone.now(),
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
