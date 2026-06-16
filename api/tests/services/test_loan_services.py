import datetime
from decimal import Decimal

from django.test import TestCase

from api.models import Account, Loan, LoanPayment, Transaction
from api.services.loan_services import (
    clear_row_anchor,
    delete_loan,
    get_loan_form_options,
    get_loans,
    match_transactions_to_loans,
    save_loan,
    save_schedule_row,
)
from api.tests.testing_factories import (
    AccountFactory,
    LoanFactory,
    TransactionFactory,
)


def make_loan(**kwargs):
    """A loan with a round $1,000 payment so scheduled amounts are predictable."""
    defaults = {
        "original_amount": Decimal("10000.00"),
        "annual_interest_rate": Decimal("0.0600"),
        "term_months": 12,
        "payment_amount": Decimal("1000.00"),
        "start_date": datetime.date(2026, 7, 1),
    }
    defaults.update(kwargs)
    loan = LoanFactory(**defaults)
    loan.generate_schedule()
    return loan


class CrudTest(TestCase):
    def cleaned(self, **kwargs):
        defaults = {
            "name": "Mortgage",
            "original_amount": Decimal("300000.00"),
            "annual_interest_rate": Decimal("0.0650"),
            "term_months": 360,
            "start_date": datetime.date(2026, 7, 1),
            "payment_amount": None,
            "principal_account": AccountFactory(
                type=Account.Type.LIABILITY, is_closed=False
            ),
            "interest_account": AccountFactory(
                type=Account.Type.EXPENSE, is_closed=False
            ),
            "payment_account": None,
            "description_match": "",
            "date_window_days": 7,
            "entity": None,
        }
        defaults.update(kwargs)
        return defaults

    def test_save_creates_loan_and_schedule(self):
        result = save_loan(self.cleaned())
        self.assertTrue(result.success)
        self.assertEqual(Loan.objects.count(), 1)
        # Schedule generated and payment computed from the terms.
        self.assertTrue(result.loan.payments.exists())
        self.assertEqual(result.loan.payment_amount, Decimal("1896.20"))

    def test_save_updates_in_place(self):
        loan = save_loan(self.cleaned()).loan
        result = save_loan(self.cleaned(name="Refi"), instance=loan)
        self.assertTrue(result.success)
        loan.refresh_from_db()
        self.assertEqual(loan.name, "Refi")
        self.assertEqual(Loan.objects.count(), 1)

    def test_delete(self):
        loan = save_loan(self.cleaned()).loan
        result = delete_loan(loan.id)
        self.assertTrue(result.success)
        self.assertEqual(Loan.objects.count(), 0)

    def test_delete_missing(self):
        result = delete_loan(99999)
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Loan not found.")

    def test_form_options_filter_by_type(self):
        AccountFactory(name="Liab", type=Account.Type.LIABILITY, is_closed=False)
        AccountFactory(name="Exp", type=Account.Type.EXPENSE, is_closed=False)
        liability, expense, payment, entities = get_loan_form_options()
        self.assertTrue(all(a.type == Account.Type.LIABILITY for a in liability))
        self.assertTrue(all(a.type == Account.Type.EXPENSE for a in expense))


class SaveScheduleRowTest(TestCase):
    def test_save_records_split_anchors_balance_and_reamortizes(self):
        loan = make_loan()  # 10k @ 6%, 12mo, $1,000 payment
        third = loan.payments.order_by("sequence")[2]

        # Saving records the split AND pins the balance baseline as of this row.
        result = save_schedule_row(
            third.id, Decimal("900.00"), Decimal("50.00"), Decimal("4000.00")
        )
        self.assertTrue(result.success)

        third.refresh_from_db()
        self.assertEqual(third.principal_amount, Decimal("900.00"))
        self.assertEqual(third.interest_amount, Decimal("50.00"))
        self.assertEqual(third.payment_amount, Decimal("950.00"))
        self.assertEqual(third.balance_override, Decimal("4000.00"))
        self.assertEqual(third.remaining_balance, Decimal("4000.00"))
        self.assertTrue(third.is_anchored)

        # Outstanding balance and the forward forecast both start from $4,000.
        loan.refresh_from_db()
        self.assertEqual(loan.remaining_balance(), Decimal("4000.00"))
        forecast = loan.payments.filter(
            sequence__gt=third.sequence, transaction__isnull=True
        ).order_by("sequence")
        self.assertTrue(forecast.exists())
        # 4000 * 0.005 = 20.00 interest on the next payment.
        self.assertEqual(forecast.first().interest_amount, Decimal("20.00"))
        self.assertEqual(forecast.last().remaining_balance, Decimal("0.00"))

    def test_save_on_forecast_row_keeps_forward_dates(self):
        loan = make_loan()  # monthly, starts 2026-07-01
        # Save the 4th payment (sequence 4 -> 2026-10-01).
        fourth = loan.payments.order_by("sequence")[3]
        self.assertEqual(fourth.date, datetime.date(2026, 10, 1))

        save_schedule_row(
            fourth.id,
            fourth.principal_amount,
            fourth.interest_amount,
            Decimal("4000.00"),
        )

        # The next forecast payment falls on the following month (2026-11-01),
        # not back near the start date.
        nxt = (
            loan.payments.filter(date__gt=fourth.date, transaction__isnull=True)
            .order_by("date")
            .first()
        )
        self.assertEqual(nxt.date, datetime.date(2026, 11, 1))

    def test_anchor_survives_later_reamortization(self):
        loan = make_loan()
        third = loan.payments.order_by("sequence")[2]
        save_schedule_row(
            third.id, third.principal_amount, third.interest_amount, Decimal("4000.00")
        )

        # A later off-schedule import re-amortizes; the anchor must still hold
        # (balance is not recomputed back to original - principal history).
        loan.generate_schedule()
        loan.refresh_from_db()
        self.assertEqual(loan.remaining_balance(), Decimal("4000.00"))

    def test_clear_anchor_restores_computed_balance(self):
        loan = make_loan()
        third = loan.payments.order_by("sequence")[2]
        save_schedule_row(
            third.id, third.principal_amount, third.interest_amount, Decimal("4000.00")
        )

        result = clear_row_anchor(third.id)
        self.assertTrue(result.success)
        loan.refresh_from_db()
        # No paid rows, no anchor -> back to the full original balance.
        self.assertEqual(loan.remaining_balance(), loan.original_amount)


class MatchScheduledTest(TestCase):
    def test_scheduled_payment_links_row(self):
        loan = make_loan()
        txn = TransactionFactory(
            amount=Decimal("-1000.00"), date=datetime.date(2026, 7, 2)
        )

        count = match_transactions_to_loans([txn])

        self.assertEqual(count, 1)
        txn.refresh_from_db()
        self.assertEqual(txn.suggested_account_id, loan.principal_account_id)
        self.assertEqual(txn.type, Transaction.TransactionType.PAYMENT)
        linked = LoanPayment.objects.get(transaction=txn)
        self.assertEqual(linked.kind, LoanPayment.Kind.SCHEDULED)

    def test_outside_date_window_no_match(self):
        make_loan(date_window_days=3)
        # 2026-07-20 is >3 days from both the 07-01 and 08-01 scheduled rows.
        txn = TransactionFactory(
            amount=Decimal("-1000.00"), date=datetime.date(2026, 7, 20)
        )
        # $1,000 is the scheduled amount but no row is within 3 days -> treated
        # as an off-schedule principal-only payment instead of a scheduled match.
        match_transactions_to_loans([txn])
        linked = LoanPayment.objects.get(transaction=txn)
        self.assertEqual(linked.kind, LoanPayment.Kind.PRINCIPAL_ONLY)


class MatchOffScheduleTest(TestCase):
    def test_principal_only_reamortizes(self):
        loan = make_loan()
        txn = TransactionFactory(
            amount=Decimal("-2000.00"), date=datetime.date(2026, 7, 15)
        )

        count = match_transactions_to_loans([txn])

        self.assertEqual(count, 1)
        linked = LoanPayment.objects.get(transaction=txn)
        self.assertEqual(linked.kind, LoanPayment.Kind.PRINCIPAL_ONLY)
        self.assertEqual(linked.principal_amount, Decimal("2000.00"))
        self.assertEqual(linked.interest_amount, Decimal("0.00"))
        loan.refresh_from_db()
        self.assertEqual(loan.remaining_balance(), Decimal("8000.00"))

    def test_off_schedule_payment_keeps_regular_cadence(self):
        """An off-cadence extra payment must not shift the regular due dates,
        else the next regular payment falls outside the match window."""
        loan = make_loan()  # monthly, starts 2026-07-01, $1,000 payment
        # July's regular (scheduled) payment is recorded.
        july = loan.payments.order_by("sequence").first()
        july.transaction = TransactionFactory(
            amount=Decimal("-1000.00"), date=datetime.date(2026, 7, 1)
        )
        july.save()

        # A random $5,000 principal payment posts on the 18th.
        rnd = TransactionFactory(
            amount=Decimal("-5000.00"), date=datetime.date(2026, 7, 18)
        )
        match_transactions_to_loans([rnd])

        # The next forecast payment stays on the original cadence (Aug 1), not
        # one month after the off-schedule payment (Aug 18).
        nxt = (
            loan.payments.filter(transaction__isnull=True).order_by("date").first()
        )
        self.assertEqual(nxt.date, datetime.date(2026, 8, 1))

    def test_payoff_closes_loan(self):
        loan = make_loan()
        txn = TransactionFactory(
            amount=Decimal("-10000.00"), date=datetime.date(2026, 7, 15)
        )

        count = match_transactions_to_loans([txn])

        self.assertEqual(count, 1)
        linked = LoanPayment.objects.get(transaction=txn)
        self.assertEqual(linked.kind, LoanPayment.Kind.PAYOFF)
        self.assertEqual(linked.principal_amount, Decimal("10000.00"))
        loan.refresh_from_db()
        self.assertTrue(loan.is_closed)


class MatchScopingTest(TestCase):
    def test_ambiguous_two_loans_skipped(self):
        make_loan(name="Loan A")
        make_loan(name="Loan B")
        # Neither loan is scoped, so an outflow matches both -> skip.
        txn = TransactionFactory(
            amount=Decimal("-1000.00"), date=datetime.date(2026, 7, 2)
        )
        count = match_transactions_to_loans([txn])
        self.assertEqual(count, 0)
        self.assertFalse(LoanPayment.objects.filter(transaction=txn).exists())

    def test_payment_account_scopes_match(self):
        bank = AccountFactory(name="Checking", is_closed=False)
        make_loan(payment_account=bank)
        other = AccountFactory(name="Other", is_closed=False)
        txn = TransactionFactory(
            account=other, amount=Decimal("-1000.00"), date=datetime.date(2026, 7, 2)
        )
        count = match_transactions_to_loans([txn])
        self.assertEqual(count, 0)

    def test_description_match_scopes_match(self):
        make_loan(description_match="WELLS MTG")
        txn = TransactionFactory(
            amount=Decimal("-1000.00"),
            description="WELLS MTG AUTOPAY",
            date=datetime.date(2026, 7, 2),
        )
        count = match_transactions_to_loans([txn])
        self.assertEqual(count, 1)

    def test_inflow_never_matches(self):
        make_loan()
        txn = TransactionFactory(
            amount=Decimal("1000.00"), date=datetime.date(2026, 7, 2)
        )
        count = match_transactions_to_loans([txn])
        self.assertEqual(count, 0)
