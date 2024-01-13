from decimal import Decimal
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