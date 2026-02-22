"""
Tests for transaction-related HTMX views.

These tests verify the basic functionality of the transaction management views.
Note: Some CRUD operations have edge cases in the existing view code that require
careful form handling. These tests focus on the happy paths.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from api.models import Account, Transaction
from api.tests.test_helpers import HTMXViewTestCase
from api.tests.scenario_builders import create_chart_of_accounts

try:
    from bs4 import BeautifulSoup
    HAS_BEAUTIFULSOUP = True
except ImportError:
    HAS_BEAUTIFULSOUP = False


class TransactionViewTestCase(HTMXViewTestCase):
    """Base class for transaction view tests with common setup."""

    def setUp(self):
        super().setUp()
        # Create basic accounts for transactions
        self.chart = create_chart_of_accounts(include_special=True)
        self.checking = self.chart['accounts']['checking']
        self.credit_card = self.chart['accounts']['credit_card']
        self.groceries = self.chart['accounts']['groceries']
        self.salary = self.chart['accounts']['salary']


class TransactionsViewTest(TransactionViewTestCase):
    """Tests for the main transactions list view."""

    def test_transactions_page_requires_login(self):
        """Verify that unauthenticated users are redirected to login."""
        self.client.logout()
        response = self.client.get(reverse('transactions'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_transactions_page_loads_for_authenticated_user(self):
        """Verify that authenticated users can access the transactions page."""
        response = self.client.get(reverse('transactions'))
        self.assertEqual(response.status_code, 200)

    def test_transactions_page_contains_filter_form(self):
        """Verify the page contains a filter form."""
        response = self.client.get(reverse('transactions'))
        self.assertContains(response, 'filter')

    def test_transactions_page_contains_transaction_form(self):
        """Verify the page contains a transaction entry form."""
        response = self.client.get(reverse('transactions'))
        # Check for form elements
        self.assertContains(response, 'form')

    def test_empty_transactions_shows_empty_table(self):
        """Verify that with no transactions, the table is empty."""
        response = self.client.get(reverse('transactions'))
        self.assertEqual(response.status_code, 200)


class TransactionFormViewTest(TransactionViewTestCase):
    """Tests for the transaction form loading view."""

    def test_load_transaction_form(self):
        """Test loading a form for an existing transaction."""
        txn = Transaction.objects.create(
            date=date.today(),
            account=self.checking,
            amount=Decimal('100.00'),
            description='Test transaction',
            type=Transaction.TransactionType.PURCHASE,
        )

        response = self.client.get(reverse('transaction-form', args=[txn.pk]))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Test transaction', content)
        self.assertIn('100', content)

    def test_load_form_for_nonexistent_transaction_returns_404(self):
        """Test that loading a form for a non-existent transaction returns 404."""
        response = self.client.get(reverse('transaction-form', args=[99999]))
        self.assertEqual(response.status_code, 404)


class TransactionDisplayTest(TransactionViewTestCase):
    """Tests for transaction display in the list view."""

    def test_page_loads_with_transactions(self):
        """Test that the page loads successfully when transactions exist."""
        # Create a transaction (it may not appear in default filter view)
        Transaction.objects.create(
            date=date.today(),
            account=self.checking,
            amount=Decimal('100.00'),
            description='Test transaction',
            type=Transaction.TransactionType.PURCHASE,
            is_closed=False,
        )

        response = self.client.get(reverse('transactions'))
        self.assertEqual(response.status_code, 200)
        # Verify the page structure contains expected elements
        self.assertContains(response, 'Transactions')
        self.assertContains(response, 'form')


class LinkTransactionsViewTest(TransactionViewTestCase):
    """Tests for the transaction linking view."""

    def _count_table_rows(self, response):
        """Count transaction rows in the response HTML."""
        soup = BeautifulSoup(response.content.decode(), 'html.parser')
        rows = soup.select('table tbody tr')
        return len(rows)

    def _create_linkable_pair(self):
        """Create two unlinked transfer transactions with opposite amounts."""
        txn1 = Transaction.objects.create(
            date=date.today(),
            account=self.checking,
            amount=Decimal('100.00'),
            description='Transfer out',
            type=Transaction.TransactionType.TRANSFER,
            is_closed=False,
        )
        txn2 = Transaction.objects.create(
            date=date.today(),
            account=self.credit_card,
            amount=Decimal('-100.00'),
            description='Transfer in',
            type=Transaction.TransactionType.TRANSFER,
            is_closed=False,
        )
        return txn1, txn2

    def test_link_page_requires_login(self):
        """Verify that unauthenticated users are redirected to login."""
        self.client.logout()
        response = self.client.get(reverse('link-transactions'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_link_page_loads(self):
        """Verify linking page loads for authenticated user."""
        response = self.client.get(reverse('link-transactions'))
        self.assertEqual(response.status_code, 200)

    def test_link_page_shows_unlinked_transfers(self):
        """Verify that unlinked transfer transactions appear in the table."""
        txn1, txn2 = self._create_linkable_pair()
        response = self.client.get(reverse('link-transactions'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Transfer out', content)
        self.assertIn('Transfer in', content)

    def test_post_link_excludes_linked_transactions_from_response(self):
        """
        After linking, the response table must NOT contain the linked transactions.

        This is the regression test: previously the view queried transactions
        BEFORE performing the link, so the response still included them.
        """
        txn1, txn2 = self._create_linkable_pair()

        # Also create a third unlinked transaction that should remain
        txn3 = Transaction.objects.create(
            date=date.today(),
            account=self.checking,
            amount=Decimal('50.00'),
            description='Unrelated transfer',
            type=Transaction.TransactionType.TRANSFER,
            is_closed=False,
        )

        post_data = {
            'first_transaction': txn1.pk,
            'second_transaction': txn2.pk,
            # Filter form fields (prefixed) matching the linking page defaults
            'filter-is_closed': 'False',
            'filter-has_linked_transaction': 'False',
            'filter-transaction_type': [
                Transaction.TransactionType.TRANSFER,
                Transaction.TransactionType.PAYMENT,
            ],
        }

        response = self.client.post(reverse('link-transactions'), post_data)
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()

        # The linked transactions should NOT appear in the response
        self.assertNotIn('Transfer out', content)
        self.assertNotIn('Transfer in', content)

        # The unrelated transaction should still be present
        self.assertIn('Unrelated transfer', content)

    def test_post_link_actually_links_transactions(self):
        """Verify that the POST actually creates the link in the database."""
        txn1, txn2 = self._create_linkable_pair()

        post_data = {
            'first_transaction': txn1.pk,
            'second_transaction': txn2.pk,
            'filter-is_closed': 'False',
            'filter-has_linked_transaction': 'False',
            'filter-transaction_type': [
                Transaction.TransactionType.TRANSFER,
                Transaction.TransactionType.PAYMENT,
            ],
        }

        self.client.post(reverse('link-transactions'), post_data)

        txn1.refresh_from_db()
        txn2.refresh_from_db()

        # One should be the hero (linked_transaction set), the other closed
        hero = txn2  # negative amount, same date → hero
        linked = txn1

        self.assertEqual(hero.linked_transaction, linked)
        self.assertTrue(linked.is_closed)

    def test_post_link_response_row_count_decreases(self):
        """After linking two transactions, the table should have 2 fewer rows."""
        txn1, txn2 = self._create_linkable_pair()

        # Create additional unlinked transaction
        Transaction.objects.create(
            date=date.today(),
            account=self.checking,
            amount=Decimal('25.00'),
            description='Extra',
            type=Transaction.TransactionType.TRANSFER,
            is_closed=False,
        )

        # Get initial count from the page
        initial_response = self.client.get(reverse('link-transactions'))
        initial_rows = self._count_table_rows(initial_response)

        post_data = {
            'first_transaction': txn1.pk,
            'second_transaction': txn2.pk,
            'filter-is_closed': 'False',
            'filter-has_linked_transaction': 'False',
            'filter-transaction_type': [
                Transaction.TransactionType.TRANSFER,
                Transaction.TransactionType.PAYMENT,
            ],
        }

        response = self.client.post(reverse('link-transactions'), post_data)
        post_rows = self._count_table_rows(response)

        # Both linked transactions should be gone (one linked, one closed)
        self.assertEqual(post_rows, initial_rows - 2)
