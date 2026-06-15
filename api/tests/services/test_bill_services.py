import datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from api.models import Account, Transaction, UtilityBill, UtilityBillRule
from api.services.bill_services import (
    ingest_message,
    match_transactions_to_bills,
    poll_bill_emails,
    resolve_bill_account,
    retry_bill,
)
from api.tests.testing_factories import AccountFactory, TransactionFactory


def make_rule(**kwargs):
    defaults = {
        "from_address": "billing@dominionenergy.com",
        "subject": "Your bill is ready",
        "account_number": "1234567890",
        "transaction_description_match": "DOMINION",
        "account": AccountFactory(type=Account.Type.EXPENSE),
    }
    defaults.update(kwargs)
    return UtilityBillRule.objects.create(**defaults)


def make_bill(**kwargs):
    defaults = {
        "source_message_id": "msg-1",
        "amount": Decimal("88.42"),
        "account_number": "1234567890",
        "status": UtilityBill.Status.PENDING,
    }
    defaults.update(kwargs)
    return UtilityBill.objects.create(**defaults)


class ResolveBillAccountTest(TestCase):
    def test_exact_account_number_match(self):
        rule = make_rule(account_number="1234567890")
        bill = make_bill(account_number="1234567890")

        match = resolve_bill_account(bill)

        self.assertEqual(match, rule)
        self.assertEqual(bill.status, UtilityBill.Status.PARSED)
        self.assertEqual(bill.account, rule.account)
        self.assertEqual(bill.rule, rule)

    def test_account_number_normalized_match(self):
        rule = make_rule(account_number="123-456-7890")
        bill = make_bill(account_number="1234567890")

        self.assertEqual(resolve_bill_account(bill), rule)
        self.assertEqual(bill.status, UtilityBill.Status.PARSED)

    def test_address_hint_fallback(self):
        rule = make_rule(account_number="0000", address_hint="Oak")
        bill = make_bill(account_number="", service_address="127 O****k Oak Lane")

        self.assertEqual(resolve_bill_account(bill), rule)
        self.assertEqual(bill.account, rule.account)

    def test_no_rule_is_unresolved(self):
        bill = make_bill(account_number="9999")

        self.assertIsNone(resolve_bill_account(bill))
        self.assertEqual(bill.status, UtilityBill.Status.UNRESOLVED)
        self.assertIsNone(bill.account)


class MatchTransactionsToBillsTest(TestCase):
    def setUp(self):
        self.bank = AccountFactory(type=Account.Type.ASSET)
        self.today = datetime.date.today()

    def _parsed_bill(self, rule, **kwargs):
        defaults = {
            "source_message_id": "m",
            "amount": Decimal("88.42"),
            "account_number": rule.account_number,
            "status": UtilityBill.Status.PARSED,
            "rule": rule,
            "account": rule.account,
            "bill_date": self.today,
        }
        defaults.update(kwargs)
        return UtilityBill.objects.create(**defaults)

    def _txn(self, **kwargs):
        defaults = {
            "account": self.bank,
            "amount": Decimal("-88.42"),
            "description": "DOMINION ENERGY PAYMENT",
            "date": self.today,
            "type": Transaction.TransactionType.PURCHASE,
        }
        defaults.update(kwargs)
        return TransactionFactory(**defaults)

    def test_in_window_match(self):
        rule = make_rule()
        bill = self._parsed_bill(rule, source_message_id="b1")
        txn = self._txn()

        count = match_transactions_to_bills([txn])

        self.assertEqual(count, 1)
        txn.refresh_from_db()
        bill.refresh_from_db()
        self.assertEqual(txn.suggested_account, rule.account)
        self.assertEqual(bill.status, UtilityBill.Status.MATCHED)
        self.assertEqual(bill.matched_transaction, txn)

    def test_out_of_window_skipped(self):
        rule = make_rule()
        self._parsed_bill(rule, source_message_id="b1", bill_date=self.today)
        txn = self._txn(date=self.today - datetime.timedelta(days=60))

        self.assertEqual(match_transactions_to_bills([txn]), 0)

    def test_null_bill_date_matches_on_amount_and_vendor(self):
        rule = make_rule()
        self._parsed_bill(rule, source_message_id="b1", bill_date=None)
        txn = self._txn(date=self.today - datetime.timedelta(days=300))

        self.assertEqual(match_transactions_to_bills([txn]), 1)

    def test_due_date_anchors_window_when_no_bill_date(self):
        rule = make_rule()
        self._parsed_bill(
            rule, source_message_id="b1", bill_date=None, due_date=self.today
        )
        in_window = self._txn(date=self.today - datetime.timedelta(days=10))
        self.assertEqual(match_transactions_to_bills([in_window]), 1)

    def test_due_date_window_excludes_far_transaction(self):
        rule = make_rule()
        self._parsed_bill(
            rule, source_message_id="b1", bill_date=None, due_date=self.today
        )
        far = self._txn(date=self.today - datetime.timedelta(days=60))
        self.assertEqual(match_transactions_to_bills([far]), 0)

    def test_due_date_preferred_over_bill_date(self):
        # Due date is in-window even though bill_date would be out-of-window.
        rule = make_rule()
        self._parsed_bill(
            rule,
            source_message_id="b1",
            bill_date=self.today - datetime.timedelta(days=120),
            due_date=self.today,
        )
        txn = self._txn(date=self.today)
        self.assertEqual(match_transactions_to_bills([txn]), 1)

    def test_payment_date_preferred_over_due_date(self):
        # Payment date is in-window; due_date would put it out-of-window.
        rule = make_rule()
        self._parsed_bill(
            rule,
            source_message_id="b1",
            bill_date=None,
            due_date=self.today - datetime.timedelta(days=120),
            payment_date=self.today,
        )
        txn = self._txn(date=self.today)
        self.assertEqual(match_transactions_to_bills([txn]), 1)

    def test_amount_collision_is_ambiguous(self):
        rule = make_rule()
        self._parsed_bill(rule, source_message_id="b1")
        self._parsed_bill(rule, source_message_id="b2")
        txn = self._txn()

        # One transaction matches two bills -> ambiguous, leave for review.
        self.assertEqual(match_transactions_to_bills([txn]), 0)

    def test_wrong_vendor_description_no_match(self):
        rule = make_rule(transaction_description_match="DOMINION")
        self._parsed_bill(rule, source_message_id="b1")
        txn = self._txn(description="CITY GAS PAYMENT")

        self.assertEqual(match_transactions_to_bills([txn]), 0)


class IngestMessageTest(TestCase):
    def test_dedupe_skips_existing_message(self):
        UtilityBill.objects.create(
            source_message_id="dup", status=UtilityBill.Status.PARSED
        )
        result = ingest_message("dup", {"from_address": "x", "text": "y"})
        self.assertIsNone(result)
        self.assertEqual(UtilityBill.objects.filter(source_message_id="dup").count(), 1)

    @patch("api.services.bill_services.parse_bill_with_gemini")
    def test_failed_record_is_retried(self, mock_parse):
        rule = make_rule()
        UtilityBill.objects.create(
            source_message_id="retry-me",
            status=UtilityBill.Status.FAILED,
            error_message="transient 503",
        )
        mock_parse.return_value = {
            "account_number": rule.account_number,
            "amount": Decimal("88.42"),
        }

        bill = ingest_message(
            "retry-me",
            {"from_address": rule.from_address, "text": "body"},
        )

        self.assertIsNotNone(bill)
        self.assertEqual(bill.status, UtilityBill.Status.PARSED)
        self.assertEqual(bill.error_message, "")
        # Still exactly one row for that message id (reused, not duplicated).
        self.assertEqual(
            UtilityBill.objects.filter(source_message_id="retry-me").count(), 1
        )

    @patch("api.services.bill_services.parse_bill_with_gemini")
    def test_ingest_parses_and_resolves(self, mock_parse):
        rule = make_rule()
        mock_parse.return_value = {
            "vendor": "Dominion Energy",
            "account_number": rule.account_number,
            "amount": Decimal("88.42"),
            "bill_date": datetime.date.today(),
        }

        bill = ingest_message(
            "new-msg",
            {"from_address": rule.from_address, "subject": "x", "text": "body"},
        )

        self.assertIsNotNone(bill)
        self.assertEqual(bill.status, UtilityBill.Status.PARSED)
        self.assertEqual(bill.account, rule.account)
        self.assertEqual(bill.amount, Decimal("88.42"))

    @patch("api.services.bill_services.parse_bill_with_gemini")
    def test_ingest_records_parse_failure(self, mock_parse):
        make_rule()
        mock_parse.side_effect = ValueError("bad json")

        bill = ingest_message(
            "fail-msg",
            {"from_address": "billing@dominionenergy.com", "text": "body"},
        )

        self.assertEqual(bill.status, UtilityBill.Status.FAILED)
        self.assertIn("bad json", bill.error_message)


class PollBillEmailsTest(TestCase):
    def test_no_rules_short_circuits(self):
        # No Gmail call should be attempted when nothing is configured.
        result = poll_bill_emails()
        self.assertEqual(result.fetched, 0)
        self.assertEqual(result.new, 0)

    @patch("api.services.bill_services.parse_bill_with_gemini")
    @patch("api.services.bill_services.get_message_text")
    @patch("api.services.bill_services.search_messages")
    @patch("api.services.bill_services.build_gmail_service")
    def test_ingests_new_message(
        self, mock_build, mock_search, mock_get, mock_parse
    ):
        rule = make_rule(account_number="123")
        mock_build.return_value = object()
        mock_search.return_value = ["m1"]
        mock_get.return_value = {
            "from_address": rule.from_address,
            "subject": rule.subject,
            "text": "body",
        }
        mock_parse.return_value = {
            "account_number": "123",
            "amount": Decimal("88.42"),
        }

        result = poll_bill_emails()

        self.assertEqual(result.fetched, 1)
        self.assertEqual(result.new, 1)
        self.assertEqual(result.parsed, 1)
        self.assertTrue(UtilityBill.objects.filter(source_message_id="m1").exists())


class RetryBillTest(TestCase):
    @patch("api.services.bill_services.parse_bill_with_gemini")
    def test_retry_reparses_failed_bill(self, mock_parse):
        rule = make_rule(account_number="123")
        bill = UtilityBill.objects.create(
            source_message_id="r1",
            status=UtilityBill.Status.FAILED,
            from_address=rule.from_address,
            raw_text="body",
            error_message="boom",
        )
        mock_parse.return_value = {
            "account_number": "123",
            "amount": Decimal("88.42"),
        }

        out = retry_bill(bill.id)

        self.assertIsNotNone(out)
        self.assertEqual(out.status, UtilityBill.Status.PARSED)
        self.assertEqual(out.error_message, "")

    def test_retry_missing_returns_none(self):
        self.assertIsNone(retry_bill(99999))


class TriggerWiringTest(TestCase):
    """The manual autotag trigger also applies utility-bill matches."""

    def test_apply_autotags_trigger_matches_bills(self):
        from api.services.journal_entry_services import (
            apply_autotags_to_open_transactions,
        )

        rule = make_rule()
        today = datetime.date.today()
        UtilityBill.objects.create(
            source_message_id="b1",
            amount=Decimal("88.42"),
            account_number=rule.account_number,
            status=UtilityBill.Status.PARSED,
            rule=rule,
            account=rule.account,
            bill_date=today,
        )
        txn = TransactionFactory(
            account=AccountFactory(type=Account.Type.ASSET),
            amount=Decimal("-88.42"),
            description="DOMINION ENERGY PAYMENT",
            date=today,
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )

        apply_autotags_to_open_transactions()

        txn.refresh_from_db()
        self.assertEqual(txn.suggested_account, rule.account)
