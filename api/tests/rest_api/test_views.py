import json
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from api.models import Account, Entity, JournalEntry, JournalEntryItem, Transaction
from api.tests.testing_factories import AccountFactory, TransactionFactory


API_KEY = "test-api-key-12345"


@override_settings(LEDGER_API_KEY=API_KEY)
class TransactionListViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Api-Key {API_KEY}")
        self.account = AccountFactory(
            name="Checking",
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
        )

    def test_list_transactions(self):
        TransactionFactory(account=self.account, amount=Decimal("100.00"))
        response = self.client.get("/api/v1/transactions/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["transactions"][0]["account"], "Checking")

    def test_filter_by_is_closed(self):
        TransactionFactory(account=self.account, is_closed=False)
        TransactionFactory(account=self.account, is_closed=True)
        response = self.client.get("/api/v1/transactions/?is_closed=false")
        self.assertEqual(response.data["count"], 1)
        self.assertFalse(response.data["transactions"][0]["is_closed"])

    def test_filter_by_account_name(self):
        other_account = AccountFactory(name="Savings")
        TransactionFactory(account=self.account)
        TransactionFactory(account=other_account)
        response = self.client.get("/api/v1/transactions/?account=Checking")
        self.assertEqual(response.data["count"], 1)

    def test_unauthenticated_returns_403(self):
        client = APIClient()
        response = client.get("/api/v1/transactions/")
        self.assertEqual(response.status_code, 403)


@override_settings(LEDGER_API_KEY=API_KEY)
class AccountListViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Api-Key {API_KEY}")

    def test_list_accounts(self):
        AccountFactory(name="Checking", type=Account.Type.ASSET, sub_type=Account.SubType.CASH)
        response = self.client.get("/api/v1/accounts/")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["count"], 1)

    def test_filter_by_type(self):
        AccountFactory(name="Income Acct", type=Account.Type.INCOME, sub_type=Account.SubType.SALARY)
        AccountFactory(name="Expense Acct", type=Account.Type.EXPENSE, sub_type=Account.SubType.PURCHASES)
        response = self.client.get("/api/v1/accounts/?type=income")
        for acct in response.data["accounts"]:
            self.assertEqual(acct["type"], "income")

    def test_filter_by_is_closed(self):
        AccountFactory(name="Open", is_closed=False)
        AccountFactory(name="Closed", is_closed=True)
        response = self.client.get("/api/v1/accounts/?is_closed=false")
        for acct in response.data["accounts"]:
            self.assertFalse(acct["is_closed"])


@override_settings(LEDGER_API_KEY=API_KEY)
class JournalEntryCreateViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Api-Key {API_KEY}")
        self.checking = AccountFactory(
            name="Checking",
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
        )
        self.groceries = AccountFactory(
            name="Groceries",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.PURCHASES,
        )

    def test_create_single_journal_entry(self):
        transaction = TransactionFactory(
            account=self.checking,
            amount=Decimal("150.00"),
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )
        data = {
            "transaction_id": transaction.id,
            "created_by": "Claude",
            "debits": [{"account": "Checking", "amount": "150.00"}],
            "credits": [{"account": "Groceries", "amount": "150.00"}],
        }
        response = self.client.post(
            "/api/v1/journal-entries/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["transaction_id"], transaction.id)
        self.assertEqual(response.data["created_by"], "Claude")
        self.assertIn("journal_entry_id", response.data)

        # Verify transaction is closed
        transaction.refresh_from_db()
        self.assertTrue(transaction.is_closed)

        # Verify created_by on JournalEntry
        je = JournalEntry.objects.get(pk=response.data["journal_entry_id"])
        self.assertEqual(je.created_by, "Claude")

    def test_create_with_new_entity(self):
        transaction = TransactionFactory(
            account=self.checking,
            amount=Decimal("150.00"),
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )
        data = {
            "transaction_id": transaction.id,
            "debits": [
                {"account": "Checking", "amount": "150.00", "entity": "Whole Foods"}
            ],
            "credits": [
                {"account": "Groceries", "amount": "150.00", "entity": "Whole Foods"}
            ],
        }
        response = self.client.post(
            "/api/v1/journal-entries/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("Whole Foods", response.data["created_entities"])
        self.assertTrue(Entity.objects.filter(name="Whole Foods").exists())

    def test_create_unbalanced_returns_400(self):
        transaction = TransactionFactory(
            account=self.checking,
            amount=Decimal("150.00"),
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )
        data = {
            "transaction_id": transaction.id,
            "debits": [{"account": "Checking", "amount": "150.00"}],
            "credits": [{"account": "Groceries", "amount": "75.00"}],
        }
        response = self.client.post(
            "/api/v1/journal-entries/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("balance", response.data["error"].lower())

    def test_create_with_negative_amount_transaction(self):
        """Negative amount: transaction account on credit side."""
        transaction = TransactionFactory(
            account=self.checking,
            amount=Decimal("-150.00"),
            is_closed=False,
            type=Transaction.TransactionType.INCOME,
        )
        data = {
            "transaction_id": transaction.id,
            "debits": [{"account": "Groceries", "amount": "150.00"}],
            "credits": [{"account": "Checking", "amount": "150.00"}],
        }
        response = self.client.post(
            "/api/v1/journal-entries/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)

        # Verify items have correct types
        je = JournalEntry.objects.get(pk=response.data["journal_entry_id"])
        items = JournalEntryItem.objects.filter(journal_entry=je)
        debit = items.get(type=JournalEntryItem.JournalEntryType.DEBIT)
        credit = items.get(type=JournalEntryItem.JournalEntryType.CREDIT)
        self.assertEqual(debit.account, self.groceries)
        self.assertEqual(credit.account, self.checking)

    def test_create_split_entry(self):
        """Split: 1 debit matching transaction, 2 credits."""
        rent = AccountFactory(
            name="Rent",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.PURCHASES,
        )
        transaction = TransactionFactory(
            account=self.checking,
            amount=Decimal("300.00"),
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )
        data = {
            "transaction_id": transaction.id,
            "debits": [{"account": "Checking", "amount": "300.00"}],
            "credits": [
                {"account": "Groceries", "amount": "100.00"},
                {"account": "Rent", "amount": "200.00"},
            ],
        }
        response = self.client.post(
            "/api/v1/journal-entries/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)

        je = JournalEntry.objects.get(pk=response.data["journal_entry_id"])
        items = JournalEntryItem.objects.filter(journal_entry=je)
        self.assertEqual(items.count(), 3)
        self.assertEqual(
            items.filter(type=JournalEntryItem.JournalEntryType.DEBIT).count(), 1
        )
        self.assertEqual(
            items.filter(type=JournalEntryItem.JournalEntryType.CREDIT).count(), 2
        )

    def test_create_with_nonexistent_transaction(self):
        data = {
            "transaction_id": 99999,
            "debits": [{"account": "Groceries", "amount": "150.00"}],
            "credits": [{"account": "Checking", "amount": "150.00"}],
        }
        response = self.client.post(
            "/api/v1/journal-entries/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_with_nonexistent_account(self):
        transaction = TransactionFactory(
            account=self.checking,
            amount=Decimal("150.00"),
            is_closed=False,
        )
        data = {
            "transaction_id": transaction.id,
            "debits": [{"account": "Nonexistent", "amount": "150.00"}],
            "credits": [{"account": "Checking", "amount": "150.00"}],
        }
        response = self.client.post(
            "/api/v1/journal-entries/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not found", response.data["error"])

    def test_create_with_closed_transaction(self):
        transaction = TransactionFactory(
            account=self.checking,
            amount=Decimal("150.00"),
            is_closed=True,
        )
        data = {
            "transaction_id": transaction.id,
            "debits": [{"account": "Groceries", "amount": "150.00"}],
            "credits": [{"account": "Checking", "amount": "150.00"}],
        }
        response = self.client.post(
            "/api/v1/journal-entries/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("already closed", response.data["error"])

    def test_bulk_create_journal_entries(self):
        t1 = TransactionFactory(
            account=self.checking,
            amount=Decimal("100.00"),
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )
        t2 = TransactionFactory(
            account=self.checking,
            amount=Decimal("200.00"),
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )
        data = {
            "journal_entries": [
                {
                    "transaction_id": t1.id,
                    "created_by": "Claude",
                    "debits": [{"account": "Checking", "amount": "100.00"}],
                    "credits": [{"account": "Groceries", "amount": "100.00"}],
                },
                {
                    "transaction_id": t2.id,
                    "created_by": "Claude",
                    "debits": [{"account": "Checking", "amount": "200.00"}],
                    "credits": [{"account": "Groceries", "amount": "200.00"}],
                },
            ]
        }
        response = self.client.post(
            "/api/v1/journal-entries/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["journal_entries"]), 2)

        # Both transactions should be closed
        t1.refresh_from_db()
        t2.refresh_from_db()
        self.assertTrue(t1.is_closed)
        self.assertTrue(t2.is_closed)

    def test_bulk_create_rolls_back_on_failure(self):
        t1 = TransactionFactory(
            account=self.checking,
            amount=Decimal("100.00"),
            is_closed=False,
            type=Transaction.TransactionType.PURCHASE,
        )
        data = {
            "journal_entries": [
                {
                    "transaction_id": t1.id,
                    "created_by": "Claude",
                    "debits": [{"account": "Checking", "amount": "100.00"}],
                    "credits": [{"account": "Groceries", "amount": "100.00"}],
                },
                {
                    "transaction_id": 99999,
                    "debits": [{"account": "Checking", "amount": "100.00"}],
                    "credits": [{"account": "Groceries", "amount": "100.00"}],
                },
            ]
        }
        response = self.client.post(
            "/api/v1/journal-entries/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

        # First transaction should NOT be closed (rolled back)
        t1.refresh_from_db()
        self.assertFalse(t1.is_closed)

    def test_unauthenticated_returns_403(self):
        client = APIClient()
        response = client.post(
            "/api/v1/journal-entries/",
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
