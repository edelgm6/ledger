"""Tests for LoanForm validation — in particular that a loan must carry at
least one matching scope (payment account and/or description match)."""

from django.test import TestCase

from api.forms import LoanForm
from api.models import Account
from api.tests.testing_factories import AccountFactory


class LoanFormScopeRequiredTest(TestCase):
    def setUp(self):
        self.liability = AccountFactory(
            type=Account.Type.LIABILITY, is_closed=False
        )
        self.expense = AccountFactory(type=Account.Type.EXPENSE, is_closed=False)
        self.bank = AccountFactory(type=Account.Type.ASSET, is_closed=False)

    def _data(self, **overrides):
        data = {
            "name": "Mortgage",
            "original_amount": "300000.00",
            "annual_interest_rate": "0.0650",
            "term_months": "360",
            "start_date": "2026-07-01",
            "payment_amount": "",
            "principal_account": str(self.liability.id),
            "interest_account": str(self.expense.id),
            "payment_account": "",
            "description_match": "",
            "date_window_days": "7",
            "entity": "",
        }
        data.update(overrides)
        return data

    def test_invalid_without_any_scope(self):
        form = LoanForm(data=self._data())
        self.assertFalse(form.is_valid())
        self.assertIn("payment_account", form.errors)

    def test_valid_with_payment_account_only(self):
        form = LoanForm(data=self._data(payment_account=str(self.bank.id)))
        self.assertTrue(form.is_valid(), form.errors)

    def test_valid_with_description_match_only(self):
        form = LoanForm(data=self._data(description_match="WELLS MTG"))
        self.assertTrue(form.is_valid(), form.errors)

    def test_blank_description_match_does_not_count(self):
        form = LoanForm(data=self._data(description_match="   "))
        self.assertFalse(form.is_valid())
