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
        rows = loan.schedule_with_running_balance()

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
            kind=LoanPayment.Kind.PRINCIPAL_ONLY,
            transaction=txn,
        )
        loan.generate_schedule()

        # Forecast rows rebuilt from the lower balance; loan still pays off.
        forecast = loan.payments.filter(transaction__isnull=True).order_by("sequence")
        self.assertTrue(forecast.exists())
        computed = loan.schedule_with_running_balance()
        self.assertEqual(computed[-1].remaining_balance, Decimal("0.00"))
        self.assertEqual(loan.remaining_balance(), Decimal("8000.00"))


class ScheduleRunningBalanceOrderingTest(TestCase):
    """The running balance rolls chronologically; the table renders by sequence.

    Those two orderings genuinely differ. An off-schedule payment takes
    max(sequence) + 1 but can be dated *earlier* than existing rows, so rolling
    the balance in sequence order would apply it after payments it actually
    precedes. This is the trap the audit flagged when the persisted
    remaining_balance column was removed.
    """

    def setUp(self):
        self.loan = LoanFactory(
            original_amount=Decimal("10000.00"),
            annual_interest_rate=Decimal("0.0000"),  # zero rate: principal == payment
            term_months=10,
            payment_amount=Decimal("1000.00"),
            start_date=datetime.date(2026, 1, 1),
        )
        self.loan.generate_schedule()

    def _pay(self, row, amount):
        """Marks a scheduled row as paid so it becomes a 'fixed' row."""
        row.transaction = TransactionFactory(amount=-amount, date=row.date)
        row.save()

    def test_rows_render_in_sequence_order(self):
        rows = self.loan.schedule_with_running_balance()
        self.assertEqual(
            [r.sequence for r in rows], sorted(r.sequence for r in rows)
        )

    def test_balance_declines_by_principal_each_row(self):
        rows = self.loan.schedule_with_running_balance()
        self.assertEqual(rows[0].remaining_balance, Decimal("9000.00"))
        self.assertEqual(rows[1].remaining_balance, Decimal("8000.00"))
        self.assertEqual(rows[-1].remaining_balance, Decimal("0.00"))

    def test_off_schedule_payment_dated_earlier_rolls_chronologically(self):
        """The regression case: highest sequence, earliest date."""
        first_two = list(self.loan.payments.order_by("sequence")[:2])
        for row in first_two:
            self._pay(row, Decimal("1000.00"))

        # An extra $500 principal payment that happened back on Jan 15 -- after
        # row 1 (Jan 1) but before row 2 (Feb 1) -- recorded late, so it takes
        # the highest sequence in the table.
        max_sequence = max(r.sequence for r in self.loan.payments.all())
        late_recorded = LoanPayment.objects.create(
            loan=self.loan,
            sequence=max_sequence + 1,
            date=datetime.date(2026, 1, 15),
            payment_amount=Decimal("500.00"),
            principal_amount=Decimal("500.00"),
            interest_amount=Decimal("0.00"),
            kind=LoanPayment.Kind.PRINCIPAL_ONLY,
            transaction=TransactionFactory(
                amount=Decimal("-500.00"), date=datetime.date(2026, 1, 15)
            ),
        )

        rows = {r.sequence: r for r in self.loan.schedule_with_running_balance()}

        # Chronological roll: Jan 1 (-1000) -> Jan 15 (-500) -> Feb 1 (-1000).
        self.assertEqual(rows[1].remaining_balance, Decimal("9000.00"))
        self.assertEqual(
            rows[late_recorded.sequence].remaining_balance,
            Decimal("8500.00"),
            "the Jan 15 payment must roll between Jan 1 and Feb 1",
        )
        self.assertEqual(
            rows[2].remaining_balance,
            Decimal("7500.00"),
            "Feb 1 follows the Jan 15 payment chronologically, not by sequence",
        )

        # And rolling by sequence instead would put the late row last, giving
        # Feb 1 a balance of 8000 and the late row 7500 -- demonstrably different.
        by_sequence = {}
        balance = self.loan.original_amount
        for row in sorted(self.loan.payments.all(), key=lambda r: r.sequence):
            balance -= row.principal_amount
            by_sequence[row.sequence] = balance
        self.assertNotEqual(
            by_sequence[2],
            rows[2].remaining_balance,
            "sequence-order and chronological rolls must differ here, or this "
            "test is not exercising the trap",
        )

    def test_balance_anchor_resets_the_roll(self):
        row = self.loan.payments.order_by("sequence")[2]
        row.balance_override = Decimal("5000.00")
        row.save()

        rows = {r.sequence: r for r in self.loan.schedule_with_running_balance()}
        self.assertEqual(rows[row.sequence].remaining_balance, Decimal("5000.00"))
