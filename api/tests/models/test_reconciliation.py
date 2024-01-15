import datetime
from decimal import Decimal
from django.test import TestCase
from django.db.utils import IntegrityError
from api.models import Reconciliation, Account, JournalEntryItem
from api.tests.testing_factories import AccountFactory, TransactionFactory, JournalEntryFactory, JournalEntryItemFactory

class ReconciliationTests(TestCase):

    def setUp(self):
        self.account = AccountFactory.create()
        self.transaction = TransactionFactory.create()

    def test_create_reconciliation(self):
        reconciliation = Reconciliation.objects.create(
            account=self.account,
            date=datetime.date.today(),
            amount=Decimal('100.00'),
            transaction=self.transaction
        )
        self.assertEqual(reconciliation.account, self.account)
        self.assertEqual(reconciliation.date, datetime.date.today())
        self.assertEqual(reconciliation.amount, Decimal('100.00'))
        self.assertEqual(reconciliation.transaction, self.transaction)
        self.assertEqual(str(reconciliation), f"{datetime.date.today()} {self.account.name}")

    def test_unique_together_constraint(self):
        # Test the unique_together constraint ('account', 'date')
        Reconciliation.objects.create(
            account=self.account,
            date=datetime.date.today(),
            amount=Decimal('100.00')
        )
        with self.assertRaises(IntegrityError):
            Reconciliation.objects.create(
                account=self.account,
                date=datetime.date.today(),
                amount=Decimal('200.00')
            )

    def test_plug_reconciliation(self):
        today = datetime.date.today()
        unrealized_account = AccountFactory(
            special_type=Account.SpecialType.UNREALIZED_GAINS_AND_LOSSES
        )
        cash_account = AccountFactory(
            name='cash',
            type=Account.Type.ASSET
        )
        income_account = AccountFactory(
            name='income',
            type=Account.Type.INCOME
        )
        journal_entry = JournalEntryFactory(
            date=today
        )
        journal_entry_item = JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=cash_account,
            amount=100,
            type=JournalEntryItem.JournalEntryType.DEBIT
        )
        journal_entry_item = JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=income_account,
            amount=100,
            type=JournalEntryItem.JournalEntryType.CREDIT
        )
        reconciliation = Reconciliation.objects.create(
            account=cash_account,
            date=today,
            amount=Decimal('200.00')
        )
        reconciliation.plug_investment_change()

        self.assertEqual(reconciliation.transaction.amount, 100)
        self.assertEqual(cash_account.get_balance(today), 200)
        self.assertEqual(unrealized_account.get_balance(today), 100)

        reconciliation.amount = Decimal('50.00')
        reconciliation.plug_investment_change()
        self.assertEqual(reconciliation.transaction.amount, Decimal('-50.00'))
        self.assertEqual(cash_account.get_balance(today), 50)
        self.assertEqual(unrealized_account.get_balance(today), Decimal('-50.00'))