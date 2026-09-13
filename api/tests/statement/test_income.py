import datetime
from decimal import Decimal
from django.test import TestCase
from api.statement import IncomeStatement
from api.models import Account, JournalEntryItem, JournalEntry, Transaction
from api.tests.scenario_builders import (
    create_closed_transaction_with_journal_entry,
    create_multi_line_journal_entry,
)
from api.tests.testing_factories import (
    AccountFactory,
    JournalEntryFactory,
    JournalEntryItemFactory,
    TransactionFactory,
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
        type=Account.Type.LIABILITY,
        sub_type=Account.SubType.SHORT_TERM_DEBT
    )
    accounts['groceries'] = Account.objects.create(
        name='5000-Groceries',
        type=Account.Type.EXPENSE,
        sub_type=Account.SubType.OPERATING
    )
    accounts['insurance'] = Account.objects.create(
        name='6000-Insurance',
        type=Account.Type.EXPENSE,
        sub_type=Account.SubType.OPERATING
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

    def test_realized_income(self):
        income_statement = IncomeStatement('2023-01-31', '2023-01-01')
        # Salary (400) + Other Income (150); excludes unrealized gains (200)
        self.assertEqual(income_statement.get_realized_income(), 550)

    def test_realized_income_matches_savings_rate_base(self):
        income_statement = IncomeStatement('2023-01-31', '2023-01-01')
        realized_income = income_statement.get_realized_income()
        savings_rate = income_statement.get_savings_rate()
        non_gains_net_income = (
            income_statement._get_non_investment_gains_net_income()
        )
        self.assertEqual(
            round(savings_rate, 2),
            round(non_gains_net_income / realized_income, 2),
        )

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


class PostTaxSavingsRateTest(TestCase):
    """Covers get_income_taxes / get_post_tax_savings_rate.

    Income taxes are identified by ``tax_kind`` (federal, state, payroll)
    so payroll counts regardless of its ``sub_type`` and property tax is
    excluded from the net-out.
    """

    def setUp(self):
        self.txn_date = '2023-01-28'
        self.cash = Account.objects.create(
            name='900-Ally', type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
        )
        self.salary = Account.objects.create(
            name='8000-Salary', type=Account.Type.INCOME,
            sub_type=Account.SubType.SALARY,
        )
        self.federal = Account.objects.create(
            name='9000-Federal Taxes', type=Account.Type.EXPENSE,
            sub_type=Account.SubType.TAX,
            tax_kind=Account.TaxKind.FEDERAL,
        )
        self.state = Account.objects.create(
            name='9100-State Taxes', type=Account.Type.EXPENSE,
            sub_type=Account.SubType.TAX,
            tax_kind=Account.TaxKind.STATE,
        )
        # Payroll deliberately lives under OPERATING to prove tax_kind,
        # not sub_type, drives inclusion.
        self.payroll = Account.objects.create(
            name='9200-Payroll Taxes', type=Account.Type.EXPENSE,
            sub_type=Account.SubType.OPERATING,
            tax_kind=Account.TaxKind.PAYROLL,
        )
        self.property_tax = Account.objects.create(
            name='9300-Property Taxes', type=Account.Type.EXPENSE,
            sub_type=Account.SubType.TAX,
            tax_kind=Account.TaxKind.PROPERTY,
        )
        self.groceries = Account.objects.create(
            name='5000-Groceries', type=Account.Type.EXPENSE,
            sub_type=Account.SubType.OPERATING,
        )

    def _expense(self, account, amount):
        create_closed_transaction_with_journal_entry(
            date=self.txn_date,
            debit_account=account,
            credit_account=self.cash,
            amount=Decimal(amount),
            transaction_account=account,
        )

    def _earn_salary(self, amount):
        create_closed_transaction_with_journal_entry(
            date=self.txn_date,
            debit_account=self.cash,
            credit_account=self.salary,
            amount=Decimal(amount),
            transaction_account=self.salary,
        )

    def _populate_standard_scenario(self):
        """Salary 1000; federal 100, state 50, payroll 30, property 40, groceries 80."""
        self._earn_salary('1000')
        self._expense(self.federal, '100')
        self._expense(self.state, '50')
        self._expense(self.payroll, '30')
        self._expense(self.property_tax, '40')
        self._expense(self.groceries, '80')

    def test_get_income_taxes_sums_federal_state_payroll_excludes_property(self):
        self._populate_standard_scenario()

        income_statement = IncomeStatement('2023-01-31', '2023-01-01')
        # 100 federal + 50 state + 30 payroll; property (40) excluded.
        self.assertEqual(income_statement.get_income_taxes(), 180)

    def test_post_tax_savings_rate(self):
        self._populate_standard_scenario()

        income_statement = IncomeStatement('2023-01-31', '2023-01-01')
        # net income 700 / after-income-tax income (1000 - 180) = 820
        self.assertEqual(
            round(income_statement.get_post_tax_savings_rate(), 4),
            round(Decimal(700) / Decimal(820), 4),
        )

    def test_post_tax_savings_rate_none_when_no_after_tax_income(self):
        # Realized income fully consumed by income taxes -> denominator 0.
        self._earn_salary('180')
        self._expense(self.federal, '100')
        self._expense(self.state, '50')
        self._expense(self.payroll, '30')

        income_statement = IncomeStatement('2023-01-31', '2023-01-01')
        self.assertEqual(income_statement.get_income_taxes(), 180)
        self.assertIsNone(income_statement.get_post_tax_savings_rate())


class MisSectionedAccountTest(TestCase):
    """Demonstrates the damage a type/sub_type mismatch does to a statement.

    Account.save() now makes this state unreachable through the model, so the
    setup forces it with queryset.update(), which bypasses save(). The test
    documents why the derived-type invariant exists and fails loudly if the
    derivation is ever removed.
    """

    def setUp(self):
        self.income_account = AccountFactory(
            name="Mis-sectioned Salary",
            type=Account.Type.INCOME,
            sub_type=Account.SubType.SALARY,
        )
        self.cash = AccountFactory(
            name="Cash For Mis-section", type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
        )
        transaction = TransactionFactory(account=self.cash, amount=Decimal("500.00"))
        journal_entry = JournalEntryFactory(
            transaction=transaction, date=datetime.date(2026, 6, 15)
        )
        JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.cash,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal("500.00"),
        )
        JournalEntryItemFactory(
            journal_entry=journal_entry,
            account=self.income_account,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=Decimal("500.00"),
        )

    def _income_statement(self):
        return IncomeStatement(
            end_date=datetime.date(2026, 12, 31), start_date=datetime.date(2026, 1, 1)
        )

    def test_consistent_account_is_counted_once_in_its_own_section(self):
        statement = self._income_statement()
        salary = [
            b for b in statement.balances
            if b.account.pk == self.income_account.pk
        ]
        self.assertEqual(len(salary), 1)
        self.assertEqual(salary[0].amount, Decimal("500.00"))

    def test_mismatched_type_drops_the_account_from_the_income_statement(self):
        # Bypass save() to manufacture the contradictory row the derivation
        # prevents: a SALARY sub_type stored as an EXPENSE.
        Account.objects.filter(pk=self.income_account.pk).update(
            type=Account.Type.EXPENSE
        )

        statement = self._income_statement()
        summaries = {m.name: m.value for m in statement.summaries}

        # The sub_type bucket still carries the amount, but it is now filed
        # under the wrong type -- the two no longer agree, which is precisely
        # the corruption Account.save() exists to prevent.
        self.assertIn("Salary", summaries)
        self.assertNotEqual(
            summaries.get("Income", 0),
            summaries.get("Salary", 0),
            "a mismatched row desynchronizes the type and sub_type totals",
        )

    def test_save_makes_the_mismatch_unreachable(self):
        self.income_account.type = Account.Type.EXPENSE
        self.income_account.save()
        self.income_account.refresh_from_db()
        self.assertEqual(self.income_account.type, Account.Type.INCOME)
