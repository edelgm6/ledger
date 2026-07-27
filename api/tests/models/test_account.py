from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.test import TestCase
from api.tests.testing_factories import AccountFactory, JournalEntryItemFactory, JournalEntryFactory
from api.models import Account, JournalEntryItem

class AccountModelTest(TestCase):
    def setUp(self):
        self.account = AccountFactory()
        # Create test accounts
        self.asset_account = AccountFactory(type=Account.Type.ASSET)
        self.income_account = AccountFactory(type=Account.Type.INCOME)

        self.income_statement_date = timezone.now().date()

        # Create test journal entries
        self.journal_entry = JournalEntryFactory(
            date=self.income_statement_date
        )

        # Create test journal entry items
        JournalEntryItemFactory(journal_entry=self.journal_entry, account=self.asset_account,
                                type=JournalEntryItem.JournalEntryType.DEBIT, amount=Decimal('100.00'))
        JournalEntryItemFactory(journal_entry=self.journal_entry, account=self.asset_account,
                                type=JournalEntryItem.JournalEntryType.CREDIT, amount=Decimal('50.00'))
        JournalEntryItemFactory(journal_entry=self.journal_entry, account=self.income_account,
                                type=JournalEntryItem.JournalEntryType.CREDIT, amount=Decimal('75.00'))
        JournalEntryItemFactory(journal_entry=self.journal_entry, account=self.income_account,
                                type=JournalEntryItem.JournalEntryType.DEBIT, amount=Decimal('25.00'))

    def test_account_creation(self):
        self.assertIsNotNone(self.account.pk, "Should create an Account instance")

    def test_account_str_representation(self):
        expected_representation = self.account.name
        self.assertEqual(str(self.account), expected_representation, "String representation should be the account name")

    def test_all_types_in_subtype_to_type_map(self):
        for type_choice in Account.Type.values:
            types = [key for key, value in Account.SUBTYPE_TO_TYPE_MAP.items() if key == type_choice]
            self.assertEqual(len(types), 1)

    def test_all_subtypes_in_subtype_to_type_map(self):
        for type_choice in Account.SubType.values:
            count = 0
            for key, value in Account.SUBTYPE_TO_TYPE_MAP.items():
                count += value.count(type_choice)

            self.assertEqual(count, 1)

    def test_get_balance_from_debit_and_credit(self):
        asset_balance = Account.get_balance_from_debit_and_credit(
            Account.Type.ASSET, debits=100, credits=50
        )
        self.assertEqual(asset_balance, 50, "Balance for an ASSET account should be debits minus credits")

        # Test for an account type where credits increase the account (e.g., LIABILITY)
        liability_balance = Account.get_balance_from_debit_and_credit(
            Account.Type.LIABILITY, debits=100, credits=150
        )
        self.assertEqual(liability_balance, 50, "Balance for a LIABILITY account should be credits minus debits")

    def test_get_balance_for_asset_account(self):
        # Test balance calculation for asset account
        end_date = timezone.now().date()
        balance = self.asset_account.get_balance(end_date)
        self.assertEqual(balance, Decimal('50.00'), "Balance should be debits minus credits for asset account")

    def test_get_balance_for_income_account(self):
        # Test balance calculation for income account within a date range
        balance = self.income_account.get_balance(end_date=self.income_statement_date, start_date=self.income_statement_date)
        self.assertEqual(balance, Decimal('50.00'), "Balance should be credits minus debits for income account")

    def test_is_investment_true_for_investment_sub_types(self):
        for sub_type in Account.INVESTMENT_SUB_TYPES:
            account = AccountFactory(type=Account.Type.ASSET, sub_type=sub_type)
            self.assertTrue(account.is_investment)

    def test_is_investment_false_for_non_investment_sub_types(self):
        for sub_type in [Account.SubType.CASH, Account.SubType.ACCOUNTS_RECEIVABLE]:
            account = AccountFactory(type=Account.Type.ASSET, sub_type=sub_type)
            self.assertFalse(account.is_investment)


class AccountCleanTest(TestCase):
    def _payable(self):
        return AccountFactory(
            type=Account.Type.LIABILITY, sub_type=Account.SubType.TAXES_PAYABLE
        )

    def _tax_account(self, payable):
        return AccountFactory(
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.TAX,
            tax_kind=Account.TaxKind.FEDERAL,
            tax_payable_account=payable,
        )

    def test_tax_rate_and_amount_mutually_exclusive(self):
        account = AccountFactory(tax_rate=Decimal("0.25"), tax_amount=Decimal("100.00"))
        with self.assertRaises(ValidationError):
            account.clean()

    def test_tax_kind_requires_payable_account(self):
        account = self._tax_account(payable=None)
        with self.assertRaises(ValidationError):
            account.clean()

    def test_payable_account_must_be_taxes_payable_subtype(self):
        wrong = AccountFactory(type=Account.Type.ASSET, sub_type=Account.SubType.CASH)
        account = self._tax_account(payable=wrong)
        with self.assertRaises(ValidationError):
            account.clean()

    def test_valid_tax_account_pairing_passes(self):
        account = self._tax_account(payable=self._payable())
        account.clean()  # should not raise


class AccountManagerTest(TestCase):
    def test_system_returns_singleton_by_role(self):
        wallet = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
            system_role=Account.SystemRole.WALLET,
        )
        self.assertEqual(
            Account.objects.system(Account.SystemRole.WALLET), wallet
        )

    def test_tax_expense_accounts_and_income_tax_divergence(self):
        kinds = {
            kind: AccountFactory(
                type=Account.Type.EXPENSE, sub_type=Account.SubType.TAX, tax_kind=kind
            )
            for kind in (
                Account.TaxKind.FEDERAL,
                Account.TaxKind.STATE,
                Account.TaxKind.PROPERTY,
                Account.TaxKind.PAYROLL,
            )
        }
        # tax_expense_accounts() = federal/state/property (excludes payroll)
        self.assertEqual(
            set(Account.objects.tax_expense_accounts()),
            {kinds[Account.TaxKind.FEDERAL], kinds[Account.TaxKind.STATE],
             kinds[Account.TaxKind.PROPERTY]},
        )
        # is_income_tax = federal/state/payroll (excludes property) — the
        # opposite trade-off; this is the intentional divergence.
        self.assertEqual(
            {k for k, a in kinds.items() if a.is_income_tax},
            {Account.TaxKind.FEDERAL, Account.TaxKind.STATE, Account.TaxKind.PAYROLL},
        )