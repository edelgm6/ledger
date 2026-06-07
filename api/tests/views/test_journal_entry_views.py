"""
Integration tests for journal entry views.

These tests verify the complete HTTP request/response flow for journal entries,
ensuring views, services, and helpers work together correctly.
"""

import re
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from django.utils import timezone

from api.models import (
    Account,
    Entity,
    JournalEntry,
    JournalEntryItem,
    Paystub,
    PaystubValue,
    S3File,
    Transaction,
)
from api.tests.testing_factories import (
    AccountFactory,
    PrefillFactory,
    TransactionFactory,
)


class JournalEntryViewTest(TestCase):
    """Tests for JournalEntryView GET and POST."""

    def setUp(self):
        """Set up test client and user."""
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")

        # Create test data
        self.asset_account = AccountFactory(
            type=Account.Type.ASSET, name="Cash", is_closed=False
        )
        self.expense_account = AccountFactory(
            type=Account.Type.EXPENSE, name="Office Supplies", is_closed=False
        )
        self.entity = Entity.objects.create(name="Test Vendor")

        self.transaction = TransactionFactory(
            account=self.asset_account,
            amount=Decimal("100.00"),
            type=Transaction.TransactionType.PURCHASE,
            is_closed=False,
        )

    def test_get_journal_entry_view(self):
        """Test GET request to journal entry main page."""
        url = reverse("journal-entries")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cash")  # Account name in table
        self.assertContains(response, "100.00")  # Transaction amount

    def xtest_post_create_journal_entry_success(self):
        """Test POST request successfully creates journal entry (skipped for now)."""
        url = reverse("journal-entries", args=[self.transaction.pk])

        # Build form data for balanced journal entry
        post_data = {
            # Filter form data (to maintain state)
            "filter-is_closed": "False",
            "filter-transaction_type": [
                Transaction.TransactionType.INCOME,
                Transaction.TransactionType.PURCHASE,
            ],
            # Metadata
            "index": "0",
            "paystub_id": "",
            # Debit formset (transaction account)
            "debits-TOTAL_FORMS": "10",
            "debits-INITIAL_FORMS": "0",
            "debits-MIN_NUM_FORMS": "0",
            "debits-MAX_NUM_FORMS": "1000",
            "debits-0-account": "Cash",
            "debits-0-amount": "100.00",
            "debits-0-entity": "Test Vendor",
            "debits-0-id": "",
            # Credit formset (offsetting account)
            "credits-TOTAL_FORMS": "10",
            "credits-INITIAL_FORMS": "0",
            "credits-MIN_NUM_FORMS": "0",
            "credits-MAX_NUM_FORMS": "1000",
            "credits-0-account": "Office Supplies",
            "credits-0-amount": "100.00",
            "credits-0-entity": "Test Vendor",
            "credits-0-id": "",
        }

        response = self.client.post(url, post_data)

        # Verify response
        self.assertEqual(response.status_code, 200)

        # Verify journal entry created
        self.transaction.refresh_from_db()
        self.assertTrue(self.transaction.is_closed)
        self.assertTrue(hasattr(self.transaction, "journal_entry"))

        # Verify journal entry items created
        journal_entry = self.transaction.journal_entry
        items = JournalEntryItem.objects.filter(journal_entry=journal_entry)
        self.assertEqual(items.count(), 2)

        debit_item = items.filter(type=JournalEntryItem.JournalEntryType.DEBIT).first()
        self.assertEqual(debit_item.amount, Decimal("100.00"))
        self.assertEqual(debit_item.account.name, "Cash")

        credit_item = items.filter(
            type=JournalEntryItem.JournalEntryType.CREDIT
        ).first()
        self.assertEqual(credit_item.amount, Decimal("100.00"))
        self.assertEqual(credit_item.account.name, "Office Supplies")

    def xtest_post_create_journal_entry_unbalanced_fails(self):
        """Test POST with unbalanced debits/credits returns error (skipped for now)."""
        url = reverse("journal-entries", args=[self.transaction.pk])

        post_data = {
            "filter-is_closed": "False",
            "filter-transaction_type": [Transaction.TransactionType.PURCHASE],
            "index": "0",
            "paystub_id": "",
            # Unbalanced: debit 100, credit 75
            "debits-TOTAL_FORMS": "10",
            "debits-INITIAL_FORMS": "0",
            "debits-MIN_NUM_FORMS": "0",
            "debits-MAX_NUM_FORMS": "1000",
            "debits-0-account": "Cash",
            "debits-0-amount": "100.00",
            "debits-0-entity": "Test Vendor",
            "debits-0-id": "",
            "credits-TOTAL_FORMS": "10",
            "credits-INITIAL_FORMS": "0",
            "credits-MIN_NUM_FORMS": "0",
            "credits-MAX_NUM_FORMS": "1000",
            "credits-0-account": "Office Supplies",
            "credits-0-amount": "75.00",  # UNBALANCED
            "credits-0-entity": "Test Vendor",
            "credits-0-id": "",
        }

        response = self.client.post(url, post_data)

        # Should return form with error (not create entry)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "must balance")

        # Verify journal entry NOT created
        self.transaction.refresh_from_db()
        self.assertFalse(self.transaction.is_closed)
        self.assertEqual(JournalEntry.objects.filter(transaction=self.transaction).count(), 0)

    def test_post_create_journal_entry_no_transaction_match_fails(self):
        """Test POST without matching transaction account/amount returns validation error."""
        url = reverse("journal-entries", args=[self.transaction.pk])

        post_data = {
            "filter-is_closed": "False",
            "filter-transaction_type": [Transaction.TransactionType.PURCHASE],
            "index": "0",
            "paystub_id": "",
            # Balanced but no item matches transaction (Cash, 100.00)
            "debits-TOTAL_FORMS": "10",
            "debits-INITIAL_FORMS": "0",
            "debits-MIN_NUM_FORMS": "0",
            "debits-MAX_NUM_FORMS": "1000",
            "debits-0-account": self.expense_account.name,  # Wrong account (should be asset)
            "debits-0-amount": "100.00",
            "debits-0-entity": "Test Vendor",
            "debits-0-id": "",
            "credits-TOTAL_FORMS": "10",
            "credits-INITIAL_FORMS": "0",
            "credits-MIN_NUM_FORMS": "0",
            "credits-MAX_NUM_FORMS": "1000",
            "credits-0-account": self.expense_account.name,
            "credits-0-amount": "100.00",
            "credits-0-entity": "Test Vendor",
            "credits-0-id": "",
        }

        response = self.client.post(url, post_data)

        # Should return form with error (status 200 with validation errors shown)
        self.assertEqual(response.status_code, 200)

        # Verify journal entry NOT created
        self.transaction.refresh_from_db()
        self.assertFalse(self.transaction.is_closed)

    def test_post_with_existing_journal_entry_doesnt_crash(self):
        """Test POST with existing journal entry doesn't crash (regression test)."""
        # Create initial journal entry
        journal_entry = JournalEntry.objects.create(
            transaction=self.transaction, date=self.transaction.date
        )
        JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            account=self.asset_account,
            amount=Decimal("100.00"),
            type=JournalEntryItem.JournalEntryType.DEBIT,
        )
        JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            account=self.expense_account,
            amount=Decimal("100.00"),
            type=JournalEntryItem.JournalEntryType.CREDIT,
        )
        self.transaction.close()

        url = reverse("journal-entries", args=[self.transaction.pk])

        # Try to POST - the important thing is it doesn't crash with AttributeError
        post_data = {
            "filter-is_closed": "False",
            "filter-transaction_type": [Transaction.TransactionType.PURCHASE],
            "index": "0",
            "paystub_id": "",
            "debits-TOTAL_FORMS": "10",
            "debits-INITIAL_FORMS": "0",
            "debits-MIN_NUM_FORMS": "0",
            "debits-MAX_NUM_FORMS": "1000",
            "debits-0-account": self.asset_account.name,
            "debits-0-amount": "100.00",
            "debits-0-entity": "Test Vendor",
            "debits-0-id": "",
            "credits-TOTAL_FORMS": "10",
            "credits-INITIAL_FORMS": "0",
            "credits-MIN_NUM_FORMS": "0",
            "credits-MAX_NUM_FORMS": "1000",
            "credits-0-account": self.expense_account.name,
            "credits-0-amount": "100.00",
            "credits-0-entity": "Test Vendor",
            "credits-0-id": "",
        }

        response = self.client.post(url, post_data)

        # Should not crash - status 200 or 400 is fine, just not 500
        self.assertIn(response.status_code, [200, 400])

    def _make_paystub(self):
        """Create an unlinked paystub with values for fill-paystub tests."""
        prefill = PrefillFactory()
        s3file = S3File.objects.create(
            prefill=prefill,
            url="https://example.com/paystub.pdf",
            user_filename="paystub.pdf",
            s3_filename="paystub.pdf",
            textract_job_id="job123",
            analysis_complete=timezone.now(),
        )
        paystub = Paystub.objects.create(
            document=s3file,
            page_id="page1",
            title="Test Paystub",
            journal_entry=None,
        )
        PaystubValue.objects.create(
            paystub=paystub,
            account=self.asset_account,
            amount=Decimal("100.00"),
            journal_entry_item_type=JournalEntryItem.JournalEntryType.DEBIT,
        )
        PaystubValue.objects.create(
            paystub=paystub,
            account=self.expense_account,
            amount=Decimal("100.00"),
            journal_entry_item_type=JournalEntryItem.JournalEntryType.CREDIT,
        )
        return paystub

    def _make_post_data(self, paystub_id, debit_amount):
        """Build a balanced journal-entry POST payload, varying only the debit amount."""
        return {
            "filter-is_closed": "False",
            "filter-transaction_type": [Transaction.TransactionType.PURCHASE],
            "index": "0",
            "paystub_id": paystub_id,
            "debits-TOTAL_FORMS": "10",
            "debits-INITIAL_FORMS": "0",
            "debits-MIN_NUM_FORMS": "0",
            "debits-MAX_NUM_FORMS": "1000",
            "debits-0-account": self.asset_account.name,
            "debits-0-amount": debit_amount,
            "debits-0-entity": "Test Vendor",
            "debits-0-id": "",
            "credits-TOTAL_FORMS": "10",
            "credits-INITIAL_FORMS": "0",
            "credits-MIN_NUM_FORMS": "0",
            "credits-MAX_NUM_FORMS": "1000",
            "credits-0-account": self.expense_account.name,
            "credits-0-amount": "100.00",
            "credits-0-entity": "Test Vendor",
            "credits-0-id": "",
        }

    def test_validation_error_preserves_paystub_id(self):
        """A field-level validation error must keep the paystub_id on the re-rendered form.

        Regression: a negative line-item amount fails validation, and the form was
        re-rendered without the paystub_id, disassociating it from the paystub.
        """
        paystub = self._make_paystub()
        url = reverse("journal-entries", args=[self.transaction.pk])

        # Negative amount -> fails MinValueValidator(0.00) -> field error
        post_data = self._make_post_data(str(paystub.id), "-100.00")

        response = self.client.post(url, post_data)

        self.assertEqual(response.status_code, 200)
        # The re-rendered form must still carry the paystub_id hidden input.
        self.assertContains(response, 'name="paystub_id"')
        self.assertContains(response, f'value="{paystub.id}"')

        # Paystub must remain unlinked since the save failed.
        paystub.refresh_from_db()
        self.assertIsNone(paystub.journal_entry)

    def test_paystub_resolved_after_correcting_validation_error(self):
        """After fixing a validation error, resubmitting links (resolves) the paystub."""
        paystub = self._make_paystub()
        url = reverse("journal-entries", args=[self.transaction.pk])

        # First submission fails (negative amount).
        failing_data = self._make_post_data(str(paystub.id), "-100.00")
        failing_response = self.client.post(url, failing_data)
        self.assertEqual(failing_response.status_code, 200)
        paystub.refresh_from_db()
        self.assertIsNone(paystub.journal_entry)

        # Simulate the browser resubmitting the re-rendered form: the corrected
        # POST carries whatever paystub_id the error response put in the hidden
        # field. If that was dropped, the paystub won't be resolved.
        match = re.search(
            r'name="paystub_id"[^>]*value="([^"]*)"',
            failing_response.content.decode(),
        )
        self.assertIsNotNone(match, "paystub_id hidden input missing from error form")
        resubmitted_paystub_id = match.group(1)

        valid_data = self._make_post_data(resubmitted_paystub_id, "100.00")
        valid_response = self.client.post(url, valid_data)
        self.assertEqual(valid_response.status_code, 200)

        paystub.refresh_from_db()
        self.transaction.refresh_from_db()
        self.assertTrue(self.transaction.is_closed)
        self.assertIsNotNone(paystub.journal_entry)
        self.assertEqual(paystub.journal_entry, self.transaction.journal_entry)


class JournalEntryTableViewTest(TestCase):
    """Tests for JournalEntryTableView (filtering)."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")

        self.account = AccountFactory()
        self.open_transaction = TransactionFactory(
            account=self.account,
            type=Transaction.TransactionType.INCOME,
            is_closed=False,
        )
        self.closed_transaction = TransactionFactory(
            account=self.account,
            type=Transaction.TransactionType.PURCHASE,
            is_closed=True,
        )

    def test_get_filtered_table(self):
        """Test GET request with filter returns correct transactions."""
        url = reverse("journal-entries-table")

        # Filter for open income transactions only
        response = self.client.get(
            url,
            {
                "filter-is_closed": "False",
                "filter-transaction_type": [Transaction.TransactionType.INCOME],
            },
        )

        self.assertEqual(response.status_code, 200)
        # Should contain open income transaction
        self.assertContains(response, str(self.open_transaction.amount))
        # Should NOT contain closed purchase transaction
        self.assertNotContains(response, str(self.closed_transaction.amount))


class JournalEntryFormViewTest(TestCase):
    """Tests for JournalEntryFormView (loading form for specific transaction)."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")

        self.account = AccountFactory()
        self.transaction = TransactionFactory(
            account=self.account,
            amount=Decimal("200.00"),
        )

    def test_get_form_for_transaction(self):
        """Test GET request loads form for specific transaction."""
        url = reverse("journal-entry-form", args=[self.transaction.pk])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Should contain transaction details
        self.assertContains(response, "200.00")
        self.assertContains(response, self.account.name)


class TriggerAutoTagViewTest(TestCase):
    """Tests for TriggerAutoTagView."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")

        self.account = AccountFactory()
        TransactionFactory(account=self.account, is_closed=False)
        TransactionFactory(account=self.account, is_closed=False)

    def test_trigger_autotag(self):
        """Test GET triggers autotag process."""
        url = reverse("trigger-autotag")

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Should return success message with count
        self.assertContains(response, "Autotag complete")
        self.assertContains(response, "2 transactions")


class PaystubTableViewTest(TestCase):
    """Tests for PaystubTableView."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")

    def test_get_paystubs_table(self):
        """Test GET request returns paystubs table."""
        url = reverse("paystub-table")

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Should return paystub table (even if empty)
        self.assertIn(b"paystub", response.content.lower())
