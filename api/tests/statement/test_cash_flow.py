from decimal import Decimal
from django.test import TestCase
from api.statement import CashFlowStatement, BalanceSheet, IncomeStatement
from api.models import Account, JournalEntry, Transaction
from api.tests.scenario_builders import (
    create_closed_transaction_with_journal_entry,
    create_multi_line_journal_entry,
)


def create_cash_flow_scenario():
    """
    Create the scenario for cash flow tests.

    This is similar to the balance sheet scenario but WITHOUT the unrealized
    earnings transaction, which is the key difference for cash flow calculations.
    """
    accounts = {}
    txn_date = '2023-01-28'

    # Create accounts
    accounts['cash'] = Account.objects.create(
        name='900-Ally',
        type=Account.Type.ASSET,
        sub_type=Account.SubType.CASH
    )
    accounts['tax'] = Account.objects.create(
        name='Taxes',
        type=Account.Type.EXPENSE,
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
    accounts['vanguard'] = Account.objects.create(
        name='7000-Vanguard',
        type=Account.Type.ASSET,
        sub_type=Account.SubType.SECURITIES_RETIREMENT
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
    accounts['mortgage'] = Account.objects.create(
        name='Mortgage',
        type=Account.Type.LIABILITY,
        sub_type=Account.SubType.LONG_TERM_DEBT
    )

    # Create transactions (without unrealized earnings)
    create_closed_transaction_with_journal_entry(
        date=txn_date,
        debit_account=accounts['tax'],
        credit_account=accounts['cash'],
        amount=Decimal('10'),
        transaction_account=accounts['tax'],
    )

    create_closed_transaction_with_journal_entry(
        date=txn_date,
        debit_account=accounts['cash'],
        credit_account=accounts['other_income'],
        amount=Decimal('150'),
        transaction_account=accounts['other_income'],
    )

    create_closed_transaction_with_journal_entry(
        date=txn_date,
        debit_account=accounts['groceries'],
        credit_account=accounts['chase'],
        amount=Decimal('100'),
        transaction_account=accounts['income'],
    )

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

    # Two retirement contributions
    for _ in range(2):
        create_closed_transaction_with_journal_entry(
            date=txn_date,
            debit_account=accounts['chase'],
            credit_account=accounts['vanguard'],
            amount=Decimal('100'),
            transaction_account=accounts['income'],
        )

    create_multi_line_journal_entry(
        date=txn_date,
        entries=[
            {'account': accounts['income'], 'type': 'credit', 'amount': Decimal('100')},
            {'account': accounts['chase'], 'type': 'credit', 'amount': Decimal('100')},
        ],
        transaction_account=accounts['income'],
        transaction_amount=Decimal('100'),
    )

    create_closed_transaction_with_journal_entry(
        date=txn_date,
        debit_account=accounts['cash'],
        credit_account=accounts['income'],
        amount=Decimal('300'),
        transaction_account=accounts['income'],
    )

    create_closed_transaction_with_journal_entry(
        date=txn_date,
        debit_account=accounts['cash'],
        credit_account=accounts['mortgage'],
        amount=Decimal('50'),
        transaction_account=accounts['cash'],
    )

    # Transfer to retirement (without the unrealized gains that balance sheet has)
    create_closed_transaction_with_journal_entry(
        date=txn_date,
        debit_account=accounts['vanguard'],
        credit_account=accounts['cash'],
        amount=Decimal('50'),
        transaction_account=accounts['cash'],
    )

    return accounts


class CashFlowTest(TestCase):

    def setUp(self):
        accounts = create_cash_flow_scenario()
        self.cash = accounts['cash']
        self.income = accounts['income']

        START_DATE = '2023-01-01'
        END_DATE = '2023-01-31'
        self.start_balance_sheet = BalanceSheet(end_date=START_DATE)
        self.end_balance_sheet = BalanceSheet(end_date=END_DATE)
        self.income_statement = IncomeStatement(
            end_date=END_DATE,
            start_date=START_DATE
        )

    def test_initialization(self):
        # Test the initialization of the CashFlowStatement object
        cash_flow_statement = CashFlowStatement(
            self.income_statement,
            self.start_balance_sheet,
            self.end_balance_sheet
        )
        self.assertIsNotNone(cash_flow_statement)

    def test_get_cash_balance(self):
        # Test the get_cash_balance method
        cash_flow_statement = CashFlowStatement(
            self.income_statement,
            self.start_balance_sheet,
            self.end_balance_sheet
        )
        cash_balance = cash_flow_statement.get_cash_balance(
            self.start_balance_sheet
        )
        self.assertEqual(cash_balance, 0)
        cash_balance = cash_flow_statement.get_cash_balance(
            self.end_balance_sheet
        )
        self.assertEqual(cash_balance, 440)

    def test_net_cash_flow_calculation(self):
        # Test the calculation of net cash flow
        cash_flow_statement = CashFlowStatement(
            self.income_statement,
            self.start_balance_sheet,
            self.end_balance_sheet
        )
        self.assertEqual(cash_flow_statement.net_cash_flow, 640)

    def test_get_balances(self):
        cash_flow_statement = CashFlowStatement(
            self.income_statement,
            self.start_balance_sheet,
            self.end_balance_sheet
        )
        balances = cash_flow_statement.get_balances()
        balance_names = [
            (balance.account, balance.amount) for balance in balances
        ]
        account = Account.objects.get(name='1200-Chase')
        self.assertIn((account, 100), balance_names)
        account = Account.objects.get(name='7000-Vanguard')
        self.assertIn((account, 150), balance_names)
        account = Account.objects.get(name='Mortgage')
        self.assertIn((account, 50), balance_names)
        realized_net_income_balance = sum([tuple[1] for tuple in balance_names if tuple[0].name == 'Realized Net Income'])
        self.assertEqual(realized_net_income_balance, 340)

    def test_levered_cash_flow(self):
        cash_flow_statement = CashFlowStatement(
            self.income_statement,
            self.start_balance_sheet,
            self.end_balance_sheet
        )
        self.assertEqual(
            390,
            cash_flow_statement.get_levered_after_tax_cash_flow()
        )

    def test_levered_cash_flow_post_retirement(self):
        cash_flow_statement = CashFlowStatement(
            self.income_statement,
            self.start_balance_sheet,
            self.end_balance_sheet
        )
        self.assertEqual(
            540,
            cash_flow_statement.get_levered_after_tax_after_retirement_cash_flow()
        )

    def test_get_balance_sheet_account_deltas(self):
        cash_flow_statement = CashFlowStatement(
            self.income_statement,
            self.start_balance_sheet,
            self.end_balance_sheet
        )
        balances = cash_flow_statement.get_balance_sheet_account_deltas()
        balance_names = [
            (balance.account, balance.amount) for balance in balances
        ]
        account = Account.objects.get(name='1200-Chase')
        self.assertIn((account, 100), balance_names)
        account = Account.objects.get(name='7000-Vanguard')
        self.assertIn((account, 150), balance_names)
        account = Account.objects.get(name='Mortgage')
        self.assertIn((account, 50), balance_names)
        account = Account.objects.get(name='900-Ally')
        self.assertIn((account, -440), balance_names)

    def test_get_cash_from_operations_balances(self):
        cash_flow_statement = CashFlowStatement(
            self.income_statement,
            self.start_balance_sheet,
            self.end_balance_sheet
        )
        balances = cash_flow_statement.get_cash_from_operations_balances()
        balance_names = [
            (balance.account, balance.amount) for balance in balances
        ]
        account = Account.objects.get(name='1200-Chase')
        self.assertIn((account, 100), balance_names)
        realized_net_income_balance = sum([tuple[1] for tuple in balance_names if tuple[0].name == 'Realized Net Income'])
        self.assertEqual(realized_net_income_balance, 340)

    def test_get_cash_from_financing_balances(self):
        cash_flow_statement = CashFlowStatement(
            self.income_statement,
            self.start_balance_sheet,
            self.end_balance_sheet
        )
        balances = cash_flow_statement.get_cash_from_financing_balances()
        balance_names = [
            (balance.account, balance.amount) for balance in balances
        ]
        account = Account.objects.get(name='Mortgage')
        self.assertIn((account, 50), balance_names)

    def test_get_cash_from_investing_balances(self):
        cash_flow_statement = CashFlowStatement(
            self.income_statement,
            self.start_balance_sheet,
            self.end_balance_sheet
        )
        balances = cash_flow_statement.get_cash_from_investing_balances()
        balance_names = [
            (balance.account, balance.amount) for balance in balances
        ]
        account = Account.objects.get(name='7000-Vanguard')
        self.assertIn((account, 150), balance_names)
