"""Tests for the loan-schedule HTMX view — in particular the single Save button
that routes to a balance anchor or a split edit based on the editable balance
cell."""

import datetime
from decimal import Decimal

from django.urls import reverse

from api.models import Account, Loan
from api.tests.test_helpers import HTMXViewTestCase
from api.tests.testing_factories import AccountFactory


def make_loan(**kwargs):
    defaults = {
        "name": "Mortgage",
        "original_amount": Decimal("10000.00"),
        "annual_interest_rate": Decimal("0.0600"),
        "term_months": 12,
        "payment_amount": Decimal("1000.00"),
        "start_date": datetime.date(2026, 7, 1),
        "principal_account": AccountFactory(
            type=Account.Type.LIABILITY, is_closed=False
        ),
        "interest_account": AccountFactory(
            type=Account.Type.EXPENSE, is_closed=False
        ),
    }
    defaults.update(kwargs)
    loan = Loan.objects.create(**defaults)
    loan.generate_schedule()
    return loan


class LoanScheduleRowSaveTest(HTMXViewTestCase):
    def _url(self, row):
        return reverse("settings-loan-schedule-row", args=[row.id])

    def test_save_anchors_balance_and_records_split(self):
        loan = make_loan()
        row = loan.payments.order_by("sequence")[3]
        response = self.client.post(
            self._url(row),
            {
                "principal_amount": "880.00",
                "interest_amount": "20.00",
                "balance_override": "4,000.00",
            },
        )
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertTrue(row.is_anchored)
        self.assertEqual(row.balance_override, Decimal("4000.00"))
        self.assertEqual(row.principal_amount, Decimal("880.00"))
        self.assertEqual(row.interest_amount, Decimal("20.00"))

    def test_every_save_creates_an_anchor(self):
        loan = make_loan()
        row = loan.payments.order_by("sequence")[3]
        # Even leaving the balance at its shown value, saving anchors the row.
        response = self.client.post(
            self._url(row),
            {
                "principal_amount": str(row.principal_amount),
                "interest_amount": str(row.interest_amount),
                "balance_override": str(row.remaining_balance),
            },
        )
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertTrue(row.is_anchored)

    def test_clear_removes_anchor(self):
        loan = make_loan()
        row = loan.payments.order_by("sequence")[3]
        # Anchor it first.
        self.client.post(
            self._url(row),
            {
                "principal_amount": str(row.principal_amount),
                "interest_amount": str(row.interest_amount),
                "balance_override": "4000.00",
            },
        )
        # Then clear.
        response = self.client.post(self._url(row), {"action": "clear_balance"})
        self.assertEqual(response.status_code, 200)
        loan.refresh_from_db()
        self.assertFalse(loan.payments.filter(balance_override__isnull=False).exists())
