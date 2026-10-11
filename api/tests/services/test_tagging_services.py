from unittest.mock import patch

from django.test import TestCase

from api.services.tagging_services import rematch_bills, tag_transactions


class TagTransactionsTest(TestCase):
    def test_runs_bills_and_loans_by_default(self):
        with patch(
            "api.services.tagging_services.bill_services.match_transactions_to_bills", autospec=True
        ) as mock_bills, patch(
            "api.services.tagging_services.loan_services.match_transactions_to_loans", autospec=True
        ) as mock_loans:
            tag_transactions(["txn"])

        mock_bills.assert_called_once_with(["txn"])
        mock_loans.assert_called_once_with(["txn"])

    def test_matcher_failure_is_isolated(self):
        # A matcher blowing up must never propagate to the caller (a failed bill
        # match can't break a CSV import or the autotag re-apply).
        with patch(
            "api.services.tagging_services.bill_services.match_transactions_to_bills",
            autospec=True,
            side_effect=Exception("boom"),
        ), patch(
            "api.services.tagging_services.loan_services.match_transactions_to_loans", autospec=True
        ) as mock_loans:
            tag_transactions(["txn"])  # must not raise

        # Loan matching still runs even after bill matching fails.
        mock_loans.assert_called_once_with(["txn"])


class RematchBillsTest(TestCase):
    def test_runs_bill_rematch(self):
        with patch(
            "api.services.tagging_services.bill_services.rematch_open_transactions",
            autospec=True,
        ) as mock_rematch:
            rematch_bills()

        mock_rematch.assert_called_once_with()

    def test_failure_is_isolated(self):
        with patch(
            "api.services.tagging_services.bill_services.rematch_open_transactions",
            autospec=True,
            side_effect=Exception("boom"),
        ):
            rematch_bills()  # must not raise
