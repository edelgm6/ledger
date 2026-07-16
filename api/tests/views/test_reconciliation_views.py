"""Tests for the reconciliation HTMX view.

Covers the two UI-facing follow-ups to the unrealized-gains guard:
- F3: a rejected gain/loss plug re-renders the table (200) with an inline alert.
- F4: the Plug button only renders for investment accounts.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from api import utils
from api.models import Account, Reconciliation, Transaction
from api.tests.test_helpers import HTMXViewTestCase
from api.tests.testing_factories import AccountFactory

try:
    from bs4 import BeautifulSoup
    HAS_BEAUTIFULSOUP = True
except ImportError:
    HAS_BEAUTIFULSOUP = False


class ReconciliationPlugViewTest(HTMXViewTestCase):
    def setUp(self):
        super().setUp()
        self.date = utils.get_last_day_of_last_month()
        self.investment_account = AccountFactory(
            name="brokerage",
            type=Account.Type.ASSET,
            sub_type=Account.SubType.SECURITIES_UNRESTRICTED,
        )
        self.receivable_account = AccountFactory(
            name="espp receivable",
            type=Account.Type.ASSET,
            sub_type=Account.SubType.ACCOUNTS_RECEIVABLE,
        )
        self.investment_recon = Reconciliation.objects.create(
            account=self.investment_account, date=self.date, amount=Decimal("200.00")
        )
        self.receivable_recon = Reconciliation.objects.create(
            account=self.receivable_account, date=self.date, amount=Decimal("200.00")
        )

    def _post_plug(self, reconciliation):
        return self.client.post(
            reverse("reconciliation"),
            {"plug": reconciliation.pk, "date": str(self.date)},
        )

    def test_plug_non_investment_shows_alert_and_writes_nothing(self):
        response = self._post_plug(self.receivable_recon)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alert-danger")
        self.assertContains(response, "breaks the cash-flow reconciliation")
        self.assertEqual(Transaction.objects.count(), 0)

    def test_plug_button_only_renders_for_investment_accounts(self):
        if not HAS_BEAUTIFULSOUP:
            self.skipTest("BeautifulSoup not installed")

        # Any post re-renders the table for the date; inspect the rendered rows.
        response = self._post_plug(self.receivable_recon)
        soup = BeautifulSoup(response.content, "html.parser")

        rows_with_plug = {}
        for row in soup.find_all("tr"):
            name_cell = row.find("td", class_="td-name")
            if not name_cell:
                continue
            has_plug = row.find("button", attrs={"name": "plug"}) is not None
            rows_with_plug[name_cell.get_text(strip=True)] = has_plug

        self.assertTrue(rows_with_plug[str(self.investment_account)])
        self.assertFalse(rows_with_plug[str(self.receivable_account)])
