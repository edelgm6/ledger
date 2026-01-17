from decimal import Decimal
from django.test import TestCase
from api.statement import IncomeStatement
from api.models import Account, JournalEntryItem, JournalEntry, Transaction
from api.tests.scenario_builders import (
    create_closed_transaction_with_journal_entry,
    create_multi_line_journal_entry,
)


def create_income_statement_scenario():
    """
    Create the standard accounts and transactions for income statement tests.

    This is similar to balance sheet scenario but uses Vanguard as an INCOME account
    for unrealized gains (different from balance sheet which uses it as ASSET).
    """
    accounts = {}
    txn_date = '2023-01-28'

    # Create accounts
    accounts['cash'] = Account.objects.create(
        name='900-Ally',
        type='asset',
        sub_type='cash'
    )
    accounts['tax'] = Account.objects.create(
        name='Taxes',
        type='expense',
        sub_type=Account.SubType.TAX
    )
    accounts['chase'] = Account.objects.create(
        name='1200-Chase',
        type='liability',
        sub_type='short_term_debt'
    )
    accounts['groceries'] = Account.objects.create(
        name='5000-Groceries',
        type='expense',
        sub_type='purchases'
    )
    accounts['insurance'] = Account.objects.create(
        name='6000-Insurance',
        type='expense',
        sub_type='purchases'
    )
    # Note: In income test, Vanguard is INCOME/UNREALIZED_INVESTMENT_GAINS
    accounts['vanguard'] = Account.objects.create(
        name='7000-Vanguard',
        type=Account.Type.INCOME,
        sub_type=Account.SubType.UNREALIZED_INVESTMENT_GAINS
    )
    accounts['income'] = Account.objects.create(
        name='8000-Income',
        type=Account.Type.INCOME,
        sub_type=Account.SubType.SALARY
    )
    accounts['other_income'] = Account.objects.create(
        name='8100-Other Income',
        type=Account.Type.INCOME,
        sub_type=Account.SubType.OTHER_INCOME
    )

    # Create transactions
    # Tax expense: Debit Taxes $10, Credit Cash $10
    create_closed_transaction_with_journal_entry(
        date=txn_date,
        debit_account=accounts['tax'],
        credit_account=accounts['cash'],
        amount=Decimal('10'),
        transaction_account=accounts['tax'],
    )

    # Other income: Debit Cash $150, Credit Other Income $150
    create_closed_transaction_with_journal_entry(
        date=txn_date,
        debit_account=accounts['cash'],
        credit_account=accounts['other_income'],
        amount=Decimal('150'),
        transaction_account=accounts['other_income'],
    )

    # Groceries: Debit Groceries $100, Credit Chase $100
    create_closed_transaction_with_journal_entry(
        date=txn_date,
        debit_account=accounts['groceries'],
        credit_account=accounts['chase'],
        amount=Decimal('100'),
        transaction_account=accounts['income'],
    )

    # Insurance: Debit Insurance $100, Credit Chase $100
    create_closed_transaction_with_journal_entry(
        date=txn_date,
        debit_account=accounts['insurance'],
        credit_account=accounts['chase'],
        amount=Decimal('100'),
        transaction_account=accounts['income'],
    )

    # Empty journal entry
    transaction = Transaction.objects.create(
        date=txn_date, amount=100, account=accounts['income'],
        is_closed=True, date_closed=txn_date
    )
    JournalEntry.objects.create(date=txn_date, transaction=transaction)

    # Two retirement contributions: Debit Chase $100, Credit Vanguard $100
    for _ in range(2):
        create_closed_transaction_with_journal_entry(
            date=txn_date,
            debit_account=accounts['chase'],
            credit_account=accounts['vanguard'],
            amount=Decimal('100'),
            transaction_account=accounts['income'],
        )

    # Multi-line entry: Credit Income $100, Credit Chase $100
    create_multi_line_journal_entry(
        date=txn_date,
        entries=[
            {'account': accounts['income'], 'type': 'credit', 'amount': Decimal('100')},
            {'account': accounts['chase'], 'type': 'credit', 'amount': Decimal('100')},
        ],
        transaction_account=accounts['income'],
        transaction_amount=Decimal('100'),
    )

    # Salary deposit: Debit Cash $300, Credit Income $300
    create_closed_transaction_with_journal_entry(
        date=txn_date,
        debit_account=accounts['cash'],
        credit_account=accounts['income'],
        amount=Decimal('300'),
        transaction_account=accounts['income'],
    )

    return accounts


class IncomeStatementTest(TestCase):

    def setUp(self):
        accounts = create_income_statement_scenario()
        self.cash = accounts['cash']
        self.income = accounts['income']

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
