"""
Playwright browser tests for journal entry UI flows.

These tests exercise the full browser stack: HTMX requests, Alpine.js state,
filter interactions, form prefill, validation errors, and the Fill Paystub flow.

Requirements:
    uv add playwright --dev
    uv run playwright install chromium

Run:
    uv run python manage.py test api.tests.e2e
"""
import datetime
import os
from decimal import Decimal

# Playwright's sync API runs an internal event loop that Django's async-safety check
# detects as an "async context". This env var disables that check for test use.
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

from django.contrib.auth.models import User
from django.test import Client, LiveServerTestCase
from django.utils import timezone
from playwright.sync_api import sync_playwright

from api.models import (
    Account,
    JournalEntryItem,
    Paystub,
    PaystubValue,
    S3File,
    Transaction,
)
from api.tests.testing_factories import (
    AccountFactory,
    EntityFactory,
    PrefillFactory,
    TransactionFactory,
)


class JournalEntryE2EBase(LiveServerTestCase):
    """Base class: spins up Playwright Chromium and handles auth cookie injection."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.context = self.browser.new_context()
        self._inject_auth_cookie()
        self.page = self.context.new_page()

    def tearDown(self):
        self.page.close()
        self.context.close()

    def _inject_auth_cookie(self):
        # Bypasses Playwright's browser isolation: injects Django's session cookie
        # directly so tests don't need a full UI login flow.
        client = Client()
        client.force_login(self.user)
        session_id = client.cookies["sessionid"].value
        self.context.add_cookies(
            [{"name": "sessionid", "value": session_id, "url": self.live_server_url}]
        )

    def goto_journal_entries(self):
        # Navigate to / to load base.html (HTMX + Alpine.js from CDN), then HTMX-navigate
        # to journal entries. Checking typeof htmx guards against CDN load delay.
        self.page.goto(self.live_server_url + "/")
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_function("typeof htmx !== 'undefined'")
        with self.page.expect_response(lambda r: "journal-entries" in r.url and "table" not in r.url):
            self.page.click("a:has-text('Entries')")
        self.page.wait_for_selector("#transactions-filter-form")

    def apply_filter(self):
        with self.page.expect_response(lambda r: "journal-entries/table" in r.url):
            self.page.click("button[type='submit']:has-text('Filter')")
        self.page.wait_for_load_state("networkidle")

    def click_transaction_row(self, transaction_id):
        with self.page.expect_response(lambda r: f"journal-entries/form/{transaction_id}" in r.url):
            self.page.click(f"tr[data-transaction-id='{transaction_id}']")
        self.page.wait_for_load_state("networkidle")

    def submit_form(self, transaction_id):
        with self.page.expect_response(
            lambda r: f"journal-entries/{transaction_id}/" in r.url
            and "form" not in r.url
            and "table" not in r.url
        ):
            self.page.click("input[type='submit'][value='Submit']")
        self.page.wait_for_load_state("networkidle")


class JournalEntryFilterTests(JournalEntryE2EBase):
    """Filters correctly include/exclude transactions from the table."""

    def setUp(self):
        super().setUp()
        self.income_account = AccountFactory(
            name="Salary Account", type=Account.Type.INCOME, is_closed=False
        )
        self.asset_account = AccountFactory(
            name="Checking Account", type=Account.Type.ASSET, is_closed=False
        )

    def test_type_filter_income_only(self):
        """Selecting only INCOME hides PURCHASE transactions."""
        TransactionFactory(
            account=self.income_account,
            amount=Decimal("500.00"),
            description="INCOME_TXN_TEST",
            type=Transaction.TransactionType.INCOME,
            is_closed=False,
        )
        TransactionFactory(
            account=self.asset_account,
            amount=Decimal("50.00"),
            description="PURCHASE_TXN_TEST",
            type=Transaction.TransactionType.PURCHASE,
            is_closed=False,
        )

        self.goto_journal_entries()

        # Both visible on default load (INCOME + PURCHASE, open)
        content = self.page.content()
        self.assertIn("INCOME_TXN_TEST", content)
        self.assertIn("PURCHASE_TXN_TEST", content)

        self.page.select_option("select[name='filter-transaction_type']", ["income"])
        self.apply_filter()

        content = self.page.content()
        self.assertIn("INCOME_TXN_TEST", content)
        self.assertNotIn("PURCHASE_TXN_TEST", content)

    def test_type_filter_multiple_types(self):
        """Selecting INCOME + PURCHASE shows both but excludes PAYMENT."""
        TransactionFactory(
            account=self.income_account,
            amount=Decimal("100.00"),
            description="MULTI_INCOME_TXN",
            type=Transaction.TransactionType.INCOME,
            is_closed=False,
        )
        TransactionFactory(
            account=self.asset_account,
            amount=Decimal("200.00"),
            description="MULTI_PURCHASE_TXN",
            type=Transaction.TransactionType.PURCHASE,
            is_closed=False,
        )
        TransactionFactory(
            account=self.asset_account,
            amount=Decimal("300.00"),
            description="MULTI_PAYMENT_TXN",
            type=Transaction.TransactionType.PAYMENT,
            is_closed=False,
        )

        self.goto_journal_entries()

        self.page.select_option(
            "select[name='filter-transaction_type']", ["income", "purchase"]
        )
        self.apply_filter()

        content = self.page.content()
        self.assertIn("MULTI_INCOME_TXN", content)
        self.assertIn("MULTI_PURCHASE_TXN", content)
        self.assertNotIn("MULTI_PAYMENT_TXN", content)

    def test_is_closed_filter(self):
        """is_closed=True shows closed transactions and hides open ones."""
        TransactionFactory(
            account=self.income_account,
            amount=Decimal("100.00"),
            description="OPEN_TXN_TEST",
            type=Transaction.TransactionType.INCOME,
            is_closed=False,
        )
        TransactionFactory(
            account=self.income_account,
            amount=Decimal("200.00"),
            description="CLOSED_TXN_TEST",
            type=Transaction.TransactionType.INCOME,
            is_closed=True,
            date_closed=datetime.date.today(),
        )

        self.goto_journal_entries()

        # Default is open only
        content = self.page.content()
        self.assertIn("OPEN_TXN_TEST", content)
        self.assertNotIn("CLOSED_TXN_TEST", content)

        self.page.select_option("select[name='filter-is_closed']", "True")
        self.apply_filter()

        content = self.page.content()
        self.assertNotIn("OPEN_TXN_TEST", content)
        self.assertIn("CLOSED_TXN_TEST", content)

    def test_date_range_filter(self):
        """date_from/date_to filter shows only transactions within the range."""
        TransactionFactory(
            account=self.income_account,
            amount=Decimal("100.00"),
            description="JAN_TXN_TEST",
            type=Transaction.TransactionType.INCOME,
            is_closed=False,
            date=datetime.date(2024, 1, 10),
        )
        TransactionFactory(
            account=self.income_account,
            amount=Decimal("200.00"),
            description="MAR_TXN_TEST",
            type=Transaction.TransactionType.INCOME,
            is_closed=False,
            date=datetime.date(2024, 3, 15),
        )

        self.goto_journal_entries()

        self.page.fill("input[name='filter-date_from']", "2024-02-01")
        self.page.fill("input[name='filter-date_to']", "2024-04-01")
        self.apply_filter()

        content = self.page.content()
        self.assertIn("MAR_TXN_TEST", content)
        self.assertNotIn("JAN_TXN_TEST", content)

    def test_combined_filter(self):
        """INCOME type + is_closed=False shows only open income transactions."""
        TransactionFactory(
            account=self.income_account,
            amount=Decimal("100.00"),
            description="COMBO_OPEN_INCOME",
            type=Transaction.TransactionType.INCOME,
            is_closed=False,
        )
        TransactionFactory(
            account=self.income_account,
            amount=Decimal("200.00"),
            description="COMBO_CLOSED_INCOME",
            type=Transaction.TransactionType.INCOME,
            is_closed=True,
            date_closed=datetime.date.today(),
        )
        TransactionFactory(
            account=self.asset_account,
            amount=Decimal("300.00"),
            description="COMBO_OPEN_PURCHASE",
            type=Transaction.TransactionType.PURCHASE,
            is_closed=False,
        )

        self.goto_journal_entries()

        self.page.select_option("select[name='filter-transaction_type']", ["income"])
        self.page.select_option("select[name='filter-is_closed']", "False")
        self.apply_filter()

        content = self.page.content()
        self.assertIn("COMBO_OPEN_INCOME", content)
        self.assertNotIn("COMBO_CLOSED_INCOME", content)
        self.assertNotIn("COMBO_OPEN_PURCHASE", content)


class JournalEntryEmptyStateTests(JournalEntryE2EBase):
    """Empty state when no transactions match the active filter."""

    def test_empty_state(self):
        """Filtering to a type with no transactions yields zero table rows."""
        account = AccountFactory(
            name="Cash", type=Account.Type.ASSET, is_closed=False
        )
        TransactionFactory(
            account=account,
            type=Transaction.TransactionType.INCOME,
            is_closed=False,
            description="SOME_INCOME_TXN",
        )

        self.goto_journal_entries()

        # Filter to PAYMENT — no payment transactions exist
        self.page.select_option("select[name='filter-transaction_type']", ["payment"])
        self.apply_filter()

        rows = self.page.locator("#transactions-table tbody tr")
        self.assertEqual(rows.count(), 0)


class JournalEntryRowAndFormTests(JournalEntryE2EBase):
    """Clicking a row prefills the form; submitting a valid entry closes the transaction."""

    def setUp(self):
        super().setUp()
        self.asset_account = AccountFactory(
            name="Checking", type=Account.Type.ASSET, is_closed=False
        )
        AccountFactory(name="Groceries", type=Account.Type.EXPENSE, is_closed=False)

    def test_row_click_prefills_form(self):
        """Clicking a row loads the journal entry form with the transaction's account and amount."""
        txn = TransactionFactory(
            account=self.asset_account,
            amount=Decimal("200.00"),
            type=Transaction.TransactionType.INCOME,
            is_closed=False,
        )

        self.goto_journal_entries()
        self.click_transaction_row(txn.id)

        debit_account = self.page.input_value("input[name='debits-0-account']")
        debit_amount = self.page.input_value("input[name='debits-0-amount']")

        self.assertEqual(debit_account, "Checking")
        self.assertIn("200", debit_amount)

    def test_successful_submit_closes_transaction(self):
        """Submitting a balanced journal entry closes the transaction and removes it from the table."""
        txn = TransactionFactory(
            account=self.asset_account,
            amount=Decimal("100.00"),
            type=Transaction.TransactionType.PURCHASE,
            is_closed=False,
        )
        EntityFactory(name="Test Vendor", is_closed=False)

        self.goto_journal_entries()
        self.click_transaction_row(txn.id)

        self.page.fill("input[name='debits-0-entity']", "Test Vendor")
        self.page.fill("input[name='credits-0-account']", "Groceries")
        self.page.fill("input[name='credits-0-entity']", "Test Vendor")

        self.submit_form(txn.id)

        txn.refresh_from_db()
        self.assertTrue(txn.is_closed)

        # Closed transaction should no longer appear under the default open filter
        rows = self.page.locator("#transactions-table tbody tr")
        self.assertEqual(rows.count(), 0)


class JournalEntryFormValidationTests(JournalEntryE2EBase):
    """Form and business-rule validation surfaces the right errors."""

    def setUp(self):
        super().setUp()
        self.asset_account = AccountFactory(
            name="Checking", type=Account.Type.ASSET, is_closed=False
        )
        AccountFactory(name="Groceries", type=Account.Type.EXPENSE, is_closed=False)
        self.txn = TransactionFactory(
            account=self.asset_account,
            amount=Decimal("100.00"),
            type=Transaction.TransactionType.PURCHASE,
            is_closed=False,
        )
        EntityFactory(name="Test Vendor", is_closed=False)

    def test_invalid_account_shows_error(self):
        """Entering a nonexistent account name marks that field invalid."""
        self.goto_journal_entries()
        self.click_transaction_row(self.txn.id)

        self.page.fill("input[name='debits-0-account']", "ZZZNOT_AN_ACCOUNT")
        self.page.fill("input[name='debits-0-entity']", "Test Vendor")
        self.page.fill("input[name='credits-0-account']", "Groceries")
        self.page.fill("input[name='credits-0-entity']", "Test Vendor")

        # wait_for_selector is more reliable than networkidle for HX-Retarget DOM swaps.
        self.page.click("input[type='submit'][value='Submit']")
        self.page.wait_for_selector("input[name='debits-0-account'].is-invalid")

        debit_account_input = self.page.locator("input[name='debits-0-account']")
        classes = debit_account_input.get_attribute("class") or ""
        self.assertIn("is-invalid", classes)

    def test_empty_entity_shows_error(self):
        """Filling account + amount but leaving entity blank marks entity invalid."""
        self.goto_journal_entries()
        self.click_transaction_row(self.txn.id)

        self.page.fill("input[name='debits-0-entity']", "")
        self.page.fill("input[name='credits-0-account']", "Groceries")
        self.page.fill("input[name='credits-0-entity']", "Test Vendor")

        # wait_for_selector is more reliable than networkidle for HX-Retarget DOM swaps.
        self.page.click("input[type='submit'][value='Submit']")
        self.page.wait_for_selector("input[name='debits-0-entity'].is-invalid")

        debit_entity_input = self.page.locator("input[name='debits-0-entity']")
        classes = debit_entity_input.get_attribute("class") or ""
        self.assertIn("is-invalid", classes)

    def test_unbalanced_entry_shows_error(self):
        """Debit total ≠ credit total shows a 'must balance' error alert."""
        self.goto_journal_entries()
        self.click_transaction_row(self.txn.id)

        self.page.fill("input[name='debits-0-entity']", "Test Vendor")

        # Credit intentionally set to 75, not 100 — unbalanced
        self.page.fill("input[name='credits-0-account']", "Groceries")
        self.page.fill("input[name='credits-0-amount']", "75")
        self.page.fill("input[name='credits-0-entity']", "Test Vendor")

        self.submit_form(self.txn.id)

        alert = self.page.locator(".alert-danger")
        self.assertTrue(alert.is_visible())
        self.assertIn("balance", alert.text_content().lower())


class JournalEntryPaystubTests(JournalEntryE2EBase):
    """Fill Paystub button prefills the form and links the paystub on submit."""

    def setUp(self):
        super().setUp()
        self.checking_account = AccountFactory(
            name="Checking", type=Account.Type.ASSET, is_closed=False
        )
        self.salary_account = AccountFactory(
            name="Salary", type=Account.Type.INCOME, is_closed=False
        )
        EntityFactory(name="My Employer", is_closed=False)

        prefill = PrefillFactory()
        self.s3file = S3File.objects.create(
            prefill=prefill,
            url="http://example.com/test-paystub.pdf",
            user_filename="May Paystub.pdf",
            s3_filename="test-paystub.pdf",
            textract_job_id="test-job-id-123",
            status=S3File.Status.COMPLETE,
            analysis_complete=timezone.now(),
        )
        self.paystub = Paystub.objects.create(
            document=self.s3file,
            page_id="1",
            title="May Paystub",
        )
        PaystubValue.objects.create(
            paystub=self.paystub,
            account=self.checking_account,
            amount=Decimal("3000.00"),
            journal_entry_item_type=JournalEntryItem.JournalEntryType.DEBIT,
        )
        PaystubValue.objects.create(
            paystub=self.paystub,
            account=self.salary_account,
            amount=Decimal("3000.00"),
            journal_entry_item_type=JournalEntryItem.JournalEntryType.CREDIT,
        )
        self.txn = TransactionFactory(
            account=self.checking_account,
            amount=Decimal("3000.00"),
            type=Transaction.TransactionType.INCOME,
            is_closed=False,
            description="PAYSTUB_TEST_TXN",
        )

    def _navigate_and_fill_paystub(self):
        # Alpine's @click on "Fill Paystub" uses selectedRowId, which is set when a
        # transaction row is clicked — so the row click must come before the paystub click.
        self.goto_journal_entries()
        self.click_transaction_row(self.txn.id)

        with self.page.expect_response(lambda r: "paystubs" in r.url and str(self.paystub.id) in r.url):
            self.page.click("tr.clickable-row:has-text('May Paystub')")
        self.page.wait_for_selector("button:has-text('Fill Paystub')")

        with self.page.expect_response(
            lambda r: f"journal-entries/form/{self.txn.id}" in r.url and "paystub_id" in r.url
        ):
            self.page.click("button:has-text('Fill Paystub')")
        self.page.wait_for_load_state("networkidle")

    def test_fill_paystub_prefills_form(self):
        """Fill Paystub populates the debit and credit fields from PaystubValues."""
        self._navigate_and_fill_paystub()

        debit_account = self.page.input_value("input[name='debits-0-account']")
        debit_amount = self.page.input_value("input[name='debits-0-amount']")
        credit_account = self.page.input_value("input[name='credits-0-account']")
        credit_amount = self.page.input_value("input[name='credits-0-amount']")

        self.assertEqual(debit_account, "Checking")
        self.assertIn("3000", debit_amount)
        self.assertEqual(credit_account, "Salary")
        self.assertIn("3000", credit_amount)

    def test_paystub_submit_links_journal_entry(self):
        """Submitting a paystub-filled form links the paystub and closes the transaction."""
        self._navigate_and_fill_paystub()

        self.page.fill("input[name='debits-0-entity']", "My Employer")
        self.page.fill("input[name='credits-0-entity']", "My Employer")

        self.submit_form(self.txn.id)

        self.txn.refresh_from_db()
        self.assertTrue(self.txn.is_closed)

        self.paystub.refresh_from_db()
        self.assertIsNotNone(self.paystub.journal_entry)
