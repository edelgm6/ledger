import datetime
from decimal import Decimal

from django.test import TestCase

from api.models import Loan, LoanPayment
from api.tests.testing_factories import LoanFactory, TransactionFactory


class ComputeMonthlyPaymentTest(TestCase):
    def test_standard_payment(self):
        loan = LoanFactory.build(
            original_amount=Decimal("300000.00"),
            annual_interest_rate=Decimal("0.0650"),
            term_months=360,
        )
        # Known fully-amortizing payment for 300k @ 6.5% over 30y.
        self.assertEqual(loan.compute_monthly_payment(), Decimal("1896.20"))

    def test_zero_interest(self):
        loan = LoanFactory.build(
            original_amount=Decimal("1200.00"),
            annual_interest_rate=Decimal("0.0000"),
            term_months=12,
        )
        self.assertEqual(loan.compute_monthly_payment(), Decimal("100.00"))


class GenerateScheduleTest(TestCase):
    def test_generates_term_rows_and_pays_off(self):
        loan = LoanFactory(
            original_amount=Decimal("10000.00"),
            annual_interest_rate=Decimal("0.0600"),
            term_months=12,
        )
        loan.generate_schedule()
        rows = list(loan.payments.order_by("sequence"))

        # Roughly the term length (final row may absorb rounding).
        self.assertGreaterEqual(len(rows), 12)
        self.assertLessEqual(len(rows), 13)
        # First payment date matches start_date; balance ends at zero.
        self.assertEqual(rows[0].date, loan.start_date)
        self.assertEqual(rows[-1].remaining_balance, Decimal("0.00"))
        # Each row's payment equals principal + interest.
        for row in rows:
            self.assertEqual(
                row.payment_amount, row.principal_amount + row.interest_amount
            )

    def test_first_interest_is_balance_times_rate(self):
        loan = LoanFactory(
            original_amount=Decimal("10000.00"),
            annual_interest_rate=Decimal("0.1200"),
            term_months=24,
        )
        loan.generate_schedule()
        first = loan.payments.order_by("sequence").first()
        # 10000 * (0.12 / 12) = 100.00
        self.assertEqual(first.interest_amount, Decimal("100.00"))

    def test_sets_computed_payment_amount(self):
        loan = LoanFactory(payment_amount=None)
        loan.generate_schedule()
        loan.refresh_from_db()
        self.assertIsNotNone(loan.payment_amount)


class RemainingBalanceTest(TestCase):
    def test_only_paid_rows_count(self):
        loan = LoanFactory(
            original_amount=Decimal("10000.00"),
            annual_interest_rate=Decimal("0.0600"),
            term_months=12,
        )
        loan.generate_schedule()
        # Nothing paid yet.
        self.assertEqual(loan.remaining_balance(), Decimal("10000.00"))

        # Link a transaction to the first row -> its principal reduces balance.
        first = loan.payments.order_by("sequence").first()
        txn = TransactionFactory(amount=Decimal("-1000.00"))
        first.transaction = txn
        first.save()
        expected = Decimal("10000.00") - first.principal_amount
        self.assertEqual(loan.remaining_balance(), expected)


class ReAmortizeTest(TestCase):
    def test_principal_payment_reamortizes_remaining(self):
        loan = LoanFactory(
            original_amount=Decimal("10000.00"),
            annual_interest_rate=Decimal("0.0600"),
            term_months=12,
        )
        loan.generate_schedule()

        # Record a $2,000 principal-only payment as a paid row, then re-amortize.
        txn = TransactionFactory(amount=Decimal("-2000.00"))
        LoanPayment.objects.create(
            loan=loan,
            sequence=100,
            date=loan.start_date,
            payment_amount=Decimal("2000.00"),
            principal_amount=Decimal("2000.00"),
            interest_amount=Decimal("0.00"),
            remaining_balance=Decimal("8000.00"),
            kind=LoanPayment.Kind.PRINCIPAL_ONLY,
            transaction=txn,
        )
        loan.generate_schedule()

        # Forecast rows rebuilt from the lower balance; loan still pays off.
        forecast = loan.payments.filter(transaction__isnull=True).order_by("sequence")
        self.assertTrue(forecast.exists())
        self.assertEqual(forecast.last().remaining_balance, Decimal("0.00"))
        self.assertEqual(loan.remaining_balance(), Decimal("8000.00"))
