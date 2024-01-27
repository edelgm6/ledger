from decimal import Decimal
from django.test import TestCase
from api.statement import IncomeStatement
from api.models import Account, JournalEntryItem, JournalEntry, Transaction


class IncomeStatementTest(TestCase):

    def setUp(self):
        self.cash = Account.objects.create(
            name='900-Ally',
            type='asset',
            sub_type='cash'
        )
        self.tax = Account.objects.create(
            name='Taxes',
            type='expense',
            sub_type=Account.SubType.TAX
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=10,
            account=self.tax
        )
        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=10,
            account=self.tax,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=10,
            account=self.cash,
            journal_entry=journal_entry
        )
        chase = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='short_term_debt'
        )
        groceries = Account.objects.create(
            name='5000-Groceries',
            type='expense',
            sub_type='purchases'
        )
        insurance = Account.objects.create(
            name='6000-Insurance',
            type='expense',
            sub_type='purchases'
        )
        vanguard = Account.objects.create(
            name='7000-Vanguard',
            type=Account.Type.INCOME,
            sub_type=Account.SubType.UNREALIZED_INVESTMENT_GAINS
        )
        self.income = Account.objects.create(
            name='8000-Income',
            type=Account.Type.INCOME,
            sub_type=Account.SubType.SALARY
        )
        other_income = Account.objects.create(
            name='8100-Other Income',
            type=Account.Type.INCOME,
            sub_type=Account.SubType.OTHER_INCOME
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=150,
            account=other_income
        )
        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=150,
            account=self.cash,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=150,
            account=other_income,
            journal_entry=journal_entry
        )

        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=self.income
        )
        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=groceries,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=self.income
        )

        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=insurance,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=self.income
        )

        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )

        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=self.income
        )

        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=vanguard,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )

        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=self.income
        )

        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=vanguard,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=self.income
        )

        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=self.income,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )

        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=self.income
        )

        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=300,
            account=self.income,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=300,
            account=self.cash,
            journal_entry=journal_entry
        )

    def test_create_income_statement(self):
        IncomeStatement('2023-01-31', '2023-01-01')

    def test_creates_balances(self):
        income_statement = IncomeStatement('2023-01-31', '2023-01-01')
        net_income = [
            balance.amount for balance in income_statement.balances if balance.account.name == 'Realized Net Income'
        ][0]
        self.assertEqual(len(income_statement.balances), 8)
        self.assertEqual(net_income, 340)

    def test_net_income(self):
        income_statement = IncomeStatement('2023-01-31', '2023-01-01')
        realized_net_income = [balance.amount for balance in income_statement.balances if balance.account.name == 'Realized Net Income'][0]
        self.assertEqual(len(income_statement.balances), 8)
        self.assertEqual(realized_net_income, 340)
        self.assertEqual(income_statement.net_income, 540)

    def test_taxable_income(self):
        income_statement = IncomeStatement('2023-01-31', '2023-01-01')
        taxable_income = income_statement.get_taxable_income()
        self.assertEqual(taxable_income, 400)

    def test_unrealized_gains(self):
        income_statement = IncomeStatement('2023-01-31', '2023-01-01')
        unrealized_gains = income_statement.get_unrealized_gains_and_losses()
        self.assertEqual(unrealized_gains, 200)

    def test_non_investment_gains_net_income(self):
        income_statement = IncomeStatement('2023-01-31', '2023-01-01')
        non_investment_income = (
            income_statement._get_non_investment_gains_net_income()
        )
        self.assertEqual(non_investment_income, 340)

    def test_savings_rate(self):
        income_statement = IncomeStatement('2023-01-31', '2023-01-01')
        savings_rate = income_statement.get_savings_rate()
        self.assertEqual(round(savings_rate, 2), round(Decimal(340/550), 2))
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=-340,
            account=self.income
        )
        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=550,
            account=self.cash,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=550,
            account=self.income,
            journal_entry=journal_entry
        )
        income_statement = IncomeStatement('2023-01-31', '2023-01-01')
        savings_rate = income_statement.get_savings_rate()
        self.assertEqual(savings_rate, None)

    def test_tax_rate(self):
        income_statement = IncomeStatement('2023-01-31', '2023-01-01')
        tax_rate = income_statement.get_tax_rate()
        self.assertEqual(tax_rate, Decimal('.025'))

        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=-400,
            account=self.income
        )
        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=400,
            account=self.cash,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=400,
            account=self.income,
            journal_entry=journal_entry
        )
        income_statement = IncomeStatement('2023-01-31', '2023-01-01')
        tax_rate = income_statement.get_tax_rate()
        self.assertEqual(tax_rate, None)
