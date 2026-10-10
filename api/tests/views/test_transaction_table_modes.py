"""The transactions table only emits a row-click request when given a URL.

`render_transaction_table` takes a `row_url`, and the linking page does not
supply one -- it selects rows with two-row-select-script instead. But the
template interpolated `{{ row_url }}` unconditionally, and Django stringifies
None, so every row on that page carried

    hx-get="Noneform/<id>/?row_index=0"
    hx-target="#form-div"

a relative path that 404s, aimed at an element the linking page does not have.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from api.models import Account, Transaction
from api.tests.testing_factories import AccountFactory, TransactionFactory
from api.views.transaction_helpers import render_transaction_table


class TransactionTableRowUrlTest(TestCase):
    def setUp(self):
        self.account = AccountFactory(
            type=Account.Type.ASSET, sub_type=Account.SubType.CASH
        )
        self.transaction = TransactionFactory(
            account=self.account,
            amount=Decimal("-10.00"),
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )

    def test_without_a_row_url_no_request_is_emitted(self):
        html = render_transaction_table(
            [self.transaction], no_highlight=True, double_row_click=True
        )
        self.assertNotIn("hx-get", html)
        self.assertNotIn("#form-div", html)

    def test_none_never_leaks_into_a_url(self):
        html = render_transaction_table([self.transaction])
        self.assertNotIn("None", html)

    def test_with_a_row_url_the_request_is_emitted(self):
        html = render_transaction_table(
            [self.transaction], row_url=reverse("journal-entries")
        )
        self.assertIn(
            f'hx-get="/journal-entries/form/{self.transaction.id}/'
            '?row_index=0"',
            html,
        )
        self.assertIn('hx-target="#form-div"', html)


class LinkingPageTableTest(TestCase):
    """End to end: the linking page's rows must not carry a broken request."""

    def setUp(self):
        self.user = User.objects.create_user(username="linking", password="p")
        self.client = Client()
        self.client.force_login(self.user)
        account = AccountFactory(
            type=Account.Type.ASSET, sub_type=Account.SubType.CASH
        )
        TransactionFactory(
            account=account,
            amount=Decimal("-10.00"),
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )

    def test_linking_rows_carry_no_row_click_request(self):
        html = self.client.get(
            reverse("link-transactions-content"), {"filter-is_closed": "False"}
        ).content.decode()
        self.assertNotIn("Noneform", html)
        self.assertNotIn("hx-get", html)

    def test_journal_entry_rows_do_carry_one(self):
        """The same helper, used with a row_url, still works."""
        html = self.client.get(reverse("journal-entries-table")).content.decode()
        self.assertIn("/journal-entries/form/", html)
