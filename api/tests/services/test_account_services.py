"""Tests for the account service layer."""

from django.test import TestCase

from api.forms import AccountForm
from api.models import Account
from api.services import account_services
from api.tests.testing_factories import AccountFactory, TransactionFactory


class GetAccountsTest(TestCase):
    def test_returns_all_accounts(self):
        AccountFactory()
        AccountFactory()
        accounts = account_services.get_accounts()
        self.assertEqual(len(accounts), 2)

    def test_open_accounts_sorted_first_then_by_name(self):
        AccountFactory(name="Zebra", is_closed=False)
        AccountFactory(name="Apple", is_closed=True)
        AccountFactory(name="Mango", is_closed=False)
        names = [a.name for a in account_services.get_accounts()]
        # Open (is_closed=False) first, alphabetical within each group.
        self.assertEqual(names, ["Mango", "Zebra", "Apple"])


class SaveAccountTest(TestCase):
    def _valid_data(self, **overrides):
        data = {
            "name": "Checking",
            "type": Account.Type.ASSET,
            "sub_type": Account.SubType.CASH,
            "entity": "",
            "csv_profile": "",
            "is_closed": False,
            "is_depreciation": False,
        }
        data.update(overrides)
        return data

    def test_create_account(self):
        form = AccountForm(self._valid_data())
        self.assertTrue(form.is_valid())
        result = account_services.save_account(form.cleaned_data)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.account)
        self.assertEqual(result.account.name, "Checking")
        self.assertTrue(Account.objects.filter(name="Checking").exists())

    def test_update_account(self):
        account = AccountFactory(
            name="Old Name", type=Account.Type.ASSET, sub_type=Account.SubType.CASH
        )
        form = AccountForm(self._valid_data(name="New Name"), instance=account)
        self.assertTrue(form.is_valid())
        result = account_services.save_account(form.cleaned_data, instance=account)

        self.assertTrue(result.success)
        account.refresh_from_db()
        self.assertEqual(account.name, "New Name")

    def test_invalid_subtype_rejected_by_form(self):
        # SALARY is an income sub_type, not valid for an asset account. The form
        # (not the service) is responsible for rejecting it.
        form = AccountForm(
            self._valid_data(type=Account.Type.ASSET, sub_type=Account.SubType.SALARY)
        )
        self.assertFalse(form.is_valid())
        self.assertIn("sub_type", form.errors)


class DeleteAccountTest(TestCase):
    def test_delete_unused_account(self):
        account = AccountFactory()
        result = account_services.delete_account(account.id)

        self.assertTrue(result.success)
        self.assertFalse(Account.objects.filter(pk=account.id).exists())

    def test_delete_blocked_when_referenced(self):
        account = AccountFactory()
        # Transaction.account is PROTECT, so this should block deletion.
        TransactionFactory(account=account)

        result = account_services.delete_account(account.id)

        self.assertFalse(result.success)
        self.assertIn("Can't delete", result.error)
        self.assertTrue(Account.objects.filter(pk=account.id).exists())

    def test_delete_missing_account(self):
        result = account_services.delete_account(999999)
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Account not found.")
