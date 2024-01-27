from django.test import TestCase
from api.statement import CashFlowStatement, BalanceSheet, IncomeStatement
from api.models import Account, JournalEntryItem, JournalEntry, Transaction


class CashFlowTest(TestCase):

    def setUp(self):
        self.cash = Account.objects.create(
            name='900-Ally',
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH
        )
        self.tax = Account.objects.create(
            name='Taxes',
            type=Account.Type.EXPENSE,
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
            type=Account.Type.ASSET,
            sub_type=Account.SubType.SECURITIES_RETIREMENT
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
        mortgage = Account.objects.create(
            name='Mortgage',
            type=Account.Type.LIABILITY,
            sub_type=Account.SubType.LONG_TERM_DEBT
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=50,
            account=self.cash
        )
        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=50,
            account=mortgage,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=50,
            account=self.cash,
            journal_entry=journal_entry
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=-50,
            account=self.cash
        )
        journal_entry = JournalEntry.objects.create(
            date='2023-01-28',
            transaction=transaction
        )
        JournalEntryItem.objects.create(
            type='credit',
            amount=50,
            account=self.cash,
            journal_entry=journal_entry
        )
        JournalEntryItem.objects.create(
            type='debit',
            amount=50,
            account=vanguard,
            journal_entry=journal_entry
        )
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
