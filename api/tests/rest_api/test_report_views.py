"""
Tests for the read-only reporting endpoints (/api/v1/reports/*).

Builds a small real ledger (income + expense within one month) and asserts the
endpoints return the statement engine's numbers as JSON, enforce API-key auth,
and validate required params.
"""

from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from api.models import Account, JournalEntry, JournalEntryItem, Transaction
from api.tests.testing_factories import (
    AccountFactory,
    EntityFactory,
    TransactionFactory,
)

API_KEY = "test-api-key-12345"
FROM_DATE = "2024-03-01"
TO_DATE = "2024-03-31"
IN_RANGE = "2024-03-15"


def _booked_entry(*, account, amount, debit_account, credit_account, entity=None):
    """Create a transaction + balanced two-item journal entry on IN_RANGE."""
    transaction = TransactionFactory(
        account=account,
        amount=amount,
        date=IN_RANGE,
        is_closed=True,
        type=Transaction.TransactionType.PURCHASE,
    )
    journal_entry = JournalEntry.objects.create(
        date=IN_RANGE, description="test entry", transaction=transaction
    )
    JournalEntryItem.objects.create(
        journal_entry=journal_entry,
        type=JournalEntryItem.JournalEntryType.DEBIT,
        amount=amount,
        account=debit_account,
        entity=entity,
    )
    JournalEntryItem.objects.create(
        journal_entry=journal_entry,
        type=JournalEntryItem.JournalEntryType.CREDIT,
        amount=amount,
        account=credit_account,
        entity=entity,
    )
    return journal_entry


@override_settings(LEDGER_API_KEY=API_KEY)
class ReportEndpointsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Api-Key {API_KEY}")

        self.cash = AccountFactory(
            name="Checking", type=Account.Type.ASSET, sub_type=Account.SubType.CASH,
            is_closed=False,
        )
        self.salary = AccountFactory(
            name="Salary", type=Account.Type.INCOME, sub_type=Account.SubType.SALARY,
            is_closed=False,
        )
        self.groceries = AccountFactory(
            name="Groceries", type=Account.Type.EXPENSE,
            sub_type=Account.SubType.OPERATING, is_closed=False,
        )
        self.whole_foods = EntityFactory(name="Whole Foods")

        # $5,000 salary income and $100 groceries expense, both in-range.
        _booked_entry(
            account=self.cash, amount=Decimal("5000.00"),
            debit_account=self.cash, credit_account=self.salary,
        )
        _booked_entry(
            account=self.cash, amount=Decimal("100.00"),
            debit_account=self.groceries, credit_account=self.cash,
            entity=self.whole_foods,
        )

    def _get(self, path, **params):
        query = {"from_date": FROM_DATE, "to_date": TO_DATE, **params}
        return self.client.get(path, data=query)

    def test_income_by_account(self):
        response = self._get("/api/v1/reports/income/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["group_by"], "account")
        self.assertEqual(Decimal(str(response.data["net_income"])), Decimal("4900.00"))
        self.assertIn("income", response.data["summary"])
        self.assertIn("expense", response.data["summary"])

    def test_income_by_entity(self):
        response = self._get("/api/v1/reports/income/", group_by="entity")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["group_by"], "entity")
        self.assertEqual(
            Decimal(str(response.data["summary"]["income_total"])),
            Decimal("5000.00"),
        )
        self.assertEqual(
            Decimal(str(response.data["summary"]["expense_total"])),
            Decimal("100.00"),
        )
        # Whole Foods should appear as an expense entity.
        expense_entities = [
            b["entity"]
            for section in response.data["summary"]["expense_sub_types"]
            for b in section["balances"]
        ]
        self.assertIn("Whole Foods", expense_entities)

    def test_balance_sheet(self):
        response = self._get("/api/v1/reports/balance-sheet/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("summary", response.data)
        self.assertIn("asset", response.data["summary"])
        self.assertIn("metrics", response.data)

    def test_cash_flow(self):
        response = self._get("/api/v1/reports/cash-flow/")
        self.assertEqual(response.status_code, 200)
        for key in (
            "cash_from_operations",
            "cash_from_financing",
            "cash_from_investing",
            "net_cash_flow",
            "operations_flows",
        ):
            self.assertIn(key, response.data)

    def test_spending_by_entity(self):
        response = self._get("/api/v1/reports/spending-by-entity/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Decimal(str(response.data["expense_total"])), Decimal("100.00")
        )

    def test_trend(self):
        response = self._get("/api/v1/reports/trend/")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data["balances"], list)
        self.assertTrue(response.data["balances"])
        self.assertIn("date", response.data["balances"][0])
        # every row carries its originating statement so consumers can rebuild a
        # single statement without double-counting cash-flow add-backs
        valid = {"income_statement", "balance_sheet", "cash_flow"}
        self.assertTrue(
            all(row.get("statement") in valid for row in response.data["balances"])
        )

    def test_account_detail(self):
        response = self._get(
            "/api/v1/reports/account-detail/", account_id=self.groceries.id
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["account"], "Groceries")
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(
            Decimal(str(response.data["items"][0]["amount"])), Decimal("100.00")
        )

    def test_account_detail_requires_account_id(self):
        response = self._get("/api/v1/reports/account-detail/")
        self.assertEqual(response.status_code, 400)

    def test_entity_detail(self):
        response = self._get(
            "/api/v1/reports/entity-detail/",
            sub_type=Account.SubType.OPERATING,
            entity_id=self.whole_foods.id,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["items"]), 1)

    def test_entity_detail_requires_sub_type(self):
        response = self._get("/api/v1/reports/entity-detail/")
        self.assertEqual(response.status_code, 400)

    def test_defaults_to_last_month_without_dates(self):
        response = self.client.get("/api/v1/reports/income/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("from_date", response.data)
        self.assertIn("to_date", response.data)

    def test_invalid_date_returns_400(self):
        # A malformed date must error, not silently fall back to the default
        # period and return data for a range the caller did not ask for.
        response = self.client.get(
            "/api/v1/reports/income/", data={"from_date": "garbage"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("from_date", response.data)

    def test_unauthenticated_returns_403(self):
        client = APIClient()
        response = client.get("/api/v1/reports/income/")
        self.assertEqual(response.status_code, 403)
