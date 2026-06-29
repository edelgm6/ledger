import datetime
from decimal import Decimal
from django.test import TestCase
from django.db.utils import IntegrityError
from api.models import Reconciliation, Account, JournalEntryItem
from api.tests.testing_factories import AccountFactory, EntityFactory, TransactionFactory, JournalEntryFactory, JournalEntryItemFactory

class ReconciliationTests(TestCase):

    def setUp(self):
        self.account = AccountFactory.create()
        self.transaction = TransactionFactory.create()

    def test_create_reconciliation(self):
        dog = 'woof'
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
            type=Account.Type.INCOME,
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
        transaction = TransactionFactory(
            date=today,
            account=income_account,
            amount=100
        )
        journal_entry = JournalEntryFactory(
            date=today,
            transaction=transaction
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
        self.assertEqual(cash_account.get_balance(end_date=today), 200)
        self.assertEqual(unrealized_account.get_balance(today,start_date=today), 100)

        reconciliation.amount = Decimal('50.00')
        reconciliation.plug_investment_change()
        self.assertEqual(reconciliation.transaction.amount, Decimal('-50.00'))
        self.assertEqual(cash_account.get_balance(today), 50)
        self.assertEqual(unrealized_account.get_balance(today,start_date=today), Decimal('-50.00'))

    def _plug_items_for_account_entity(self, entity):
        today = datetime.date.today()
        AccountFactory(
            type=Account.Type.INCOME,
            special_type=Account.SpecialType.UNREALIZED_GAINS_AND_LOSSES
        )
        investment_account = AccountFactory(
            name='vanguard',
            type=Account.Type.ASSET,
            entity=entity
        )
        reconciliation = Reconciliation.objects.create(
            account=investment_account,
            date=today,
            amount=Decimal('200.00')
        )
        reconciliation.plug_investment_change()

        return JournalEntryItem.objects.filter(
            journal_entry=reconciliation.transaction.journal_entry
        )

    def test_plug_tags_account_default_entity(self):
        entity = EntityFactory()
        items = self._plug_items_for_account_entity(entity)
        self.assertEqual(items.count(), 2)
        for item in items:
            self.assertEqual(item.entity, entity)

    def test_plug_without_default_entity_leaves_entity_null(self):
        items = self._plug_items_for_account_entity(None)
        self.assertEqual(items.count(), 2)
        for item in items:
            self.assertIsNone(item.entity)