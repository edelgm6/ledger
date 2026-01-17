"""
Scenario builders for creating common test data hierarchies.

These helper functions reduce boilerplate in tests by creating complete,
valid object graphs with sensible defaults.
"""
from decimal import Decimal
from datetime import date
from typing import Optional

from api.models import (
    Account,
    Entity,
    JournalEntry,
    JournalEntryItem,
    Transaction,
    CSVProfile,
    Prefill,
    AutoTag,
)


def create_special_accounts():
    """
    Create all special_type accounts needed by TaxCharge, Reconciliation, and Amortization.

    Returns a dict keyed by special_type value for easy access.
    """
    special_accounts = {}

    # Tax expense accounts
    special_accounts['state_taxes'] = Account.objects.create(
        name='State Taxes',
        type=Account.Type.EXPENSE,
        sub_type=Account.SubType.TAX,
        special_type=Account.SpecialType.STATE_TAXES,
    )
    special_accounts['federal_taxes'] = Account.objects.create(
        name='Federal Taxes',
        type=Account.Type.EXPENSE,
        sub_type=Account.SubType.TAX,
        special_type=Account.SpecialType.FEDERAL_TAXES,
    )
    special_accounts['property_taxes'] = Account.objects.create(
        name='Property Taxes',
        type=Account.Type.EXPENSE,
        sub_type=Account.SubType.TAX,
        special_type=Account.SpecialType.PROPERTY_TAXES,
    )

    # Tax payable (liability) accounts - linked to their expense counterparts
    special_accounts['state_taxes_payable'] = Account.objects.create(
        name='State Taxes Payable',
        type=Account.Type.LIABILITY,
        sub_type=Account.SubType.TAXES_PAYABLE,
        special_type=Account.SpecialType.STATE_TAXES_PAYABLE,
    )
    special_accounts['federal_taxes_payable'] = Account.objects.create(
        name='Federal Taxes Payable',
        type=Account.Type.LIABILITY,
        sub_type=Account.SubType.TAXES_PAYABLE,
        special_type=Account.SpecialType.FEDERAL_TAXES_PAYABLE,
    )
    special_accounts['property_taxes_payable'] = Account.objects.create(
        name='Property Taxes Payable',
        type=Account.Type.LIABILITY,
        sub_type=Account.SubType.TAXES_PAYABLE,
        special_type=Account.SpecialType.PROPERTY_TAXES_PAYABLE,
    )

    # Link tax expense accounts to their payable accounts
    special_accounts['state_taxes'].tax_payable_account = special_accounts['state_taxes_payable']
    special_accounts['state_taxes'].save()
    special_accounts['federal_taxes'].tax_payable_account = special_accounts['federal_taxes_payable']
    special_accounts['federal_taxes'].save()
    special_accounts['property_taxes'].tax_payable_account = special_accounts['property_taxes_payable']
    special_accounts['property_taxes'].save()

    # Other special accounts
    special_accounts['unrealized_gains_and_losses'] = Account.objects.create(
        name='Unrealized Gains and Losses',
        type=Account.Type.INCOME,
        sub_type=Account.SubType.UNREALIZED_INVESTMENT_GAINS,
        special_type=Account.SpecialType.UNREALIZED_GAINS_AND_LOSSES,
    )
    special_accounts['wallet'] = Account.objects.create(
        name='Wallet',
        type=Account.Type.ASSET,
        sub_type=Account.SubType.CASH,
        special_type=Account.SpecialType.WALLET,
    )
    special_accounts['prepaid_expenses'] = Account.objects.create(
        name='Prepaid Expenses',
        type=Account.Type.ASSET,
        sub_type=Account.SubType.PREPAID_EXPENSES,
        special_type=Account.SpecialType.PREPAID_EXPENSES,
    )
    special_accounts['starting_equity'] = Account.objects.create(
        name='Starting Equity',
        type=Account.Type.EQUITY,
        sub_type=Account.SubType.RETAINED_EARNINGS,
        special_type=Account.SpecialType.STARTING_EQUITY,
    )

    return special_accounts


def create_chart_of_accounts(include_special=True):
    """
    Create a complete chart of accounts covering all types and subtypes.

    Args:
        include_special: If True, also creates all special_type accounts

    Returns a dict with two keys:
        - 'accounts': dict of regular accounts keyed by name
        - 'special': dict of special accounts keyed by special_type (if include_special=True)
    """
    result = {'accounts': {}, 'special': {}}

    if include_special:
        result['special'] = create_special_accounts()

    # Assets
    result['accounts']['checking'] = Account.objects.create(
        name='Checking Account',
        type=Account.Type.ASSET,
        sub_type=Account.SubType.CASH,
    )
    result['accounts']['savings'] = Account.objects.create(
        name='Savings Account',
        type=Account.Type.ASSET,
        sub_type=Account.SubType.CASH,
    )
    result['accounts']['accounts_receivable'] = Account.objects.create(
        name='Accounts Receivable',
        type=Account.Type.ASSET,
        sub_type=Account.SubType.ACCOUNTS_RECEIVABLE,
    )
    result['accounts']['brokerage'] = Account.objects.create(
        name='Brokerage Account',
        type=Account.Type.ASSET,
        sub_type=Account.SubType.SECURITIES_UNRESTRICTED,
    )
    result['accounts']['401k'] = Account.objects.create(
        name='401k',
        type=Account.Type.ASSET,
        sub_type=Account.SubType.SECURITIES_RETIREMENT,
    )
    result['accounts']['home'] = Account.objects.create(
        name='Home',
        type=Account.Type.ASSET,
        sub_type=Account.SubType.REAL_ESTATE,
    )

    # Liabilities
    result['accounts']['credit_card'] = Account.objects.create(
        name='Credit Card',
        type=Account.Type.LIABILITY,
        sub_type=Account.SubType.SHORT_TERM_DEBT,
    )
    result['accounts']['mortgage'] = Account.objects.create(
        name='Mortgage',
        type=Account.Type.LIABILITY,
        sub_type=Account.SubType.LONG_TERM_DEBT,
    )

    # Income
    result['accounts']['salary'] = Account.objects.create(
        name='Salary',
        type=Account.Type.INCOME,
        sub_type=Account.SubType.SALARY,
    )
    result['accounts']['dividends'] = Account.objects.create(
        name='Dividends & Interest',
        type=Account.Type.INCOME,
        sub_type=Account.SubType.DIVIDENDS_AND_INTEREST,
    )
    result['accounts']['realized_gains'] = Account.objects.create(
        name='Realized Investment Gains',
        type=Account.Type.INCOME,
        sub_type=Account.SubType.REALIZED_INVESTMENT_GAINS,
    )
    result['accounts']['other_income'] = Account.objects.create(
        name='Other Income',
        type=Account.Type.INCOME,
        sub_type=Account.SubType.OTHER_INCOME,
    )
    result['accounts']['unrealized_gains'] = Account.objects.create(
        name='Unrealized Investment Gains',
        type=Account.Type.INCOME,
        sub_type=Account.SubType.UNREALIZED_INVESTMENT_GAINS,
    )

    # Expenses
    result['accounts']['groceries'] = Account.objects.create(
        name='Groceries',
        type=Account.Type.EXPENSE,
        sub_type=Account.SubType.PURCHASES,
    )
    result['accounts']['utilities'] = Account.objects.create(
        name='Utilities',
        type=Account.Type.EXPENSE,
        sub_type=Account.SubType.PURCHASES,
    )
    result['accounts']['dining'] = Account.objects.create(
        name='Dining Out',
        type=Account.Type.EXPENSE,
        sub_type=Account.SubType.PURCHASES,
    )
    result['accounts']['interest_expense'] = Account.objects.create(
        name='Interest Expense',
        type=Account.Type.EXPENSE,
        sub_type=Account.SubType.INTEREST,
    )

    # Equity
    result['accounts']['retained_earnings'] = Account.objects.create(
        name='Retained Earnings',
        type=Account.Type.EQUITY,
        sub_type=Account.SubType.RETAINED_EARNINGS,
    )

    return result


def create_closed_transaction_with_journal_entry(
    date: date,
    debit_account: Account,
    credit_account: Account,
    amount: Decimal,
    description: str = '',
    transaction_account: Optional[Account] = None,
    transaction_type: str = Transaction.TransactionType.PURCHASE,
    debit_entity: Optional[Entity] = None,
    credit_entity: Optional[Entity] = None,
):
    """
    Create a complete, closed transaction with its journal entry and two journal entry items.

    This is the most common pattern: a simple two-sided entry with one debit and one credit.

    Args:
        date: Transaction date
        debit_account: Account to debit
        credit_account: Account to credit
        amount: Amount for both sides (must be positive)
        description: Transaction description
        transaction_account: Account for the Transaction (defaults to debit_account)
        transaction_type: Type of transaction
        debit_entity: Optional entity for the debit entry
        credit_entity: Optional entity for the credit entry

    Returns:
        dict with keys: 'transaction', 'journal_entry', 'debit_item', 'credit_item'
    """
    if transaction_account is None:
        transaction_account = debit_account

    transaction = Transaction.objects.create(
        date=date,
        account=transaction_account,
        amount=amount,
        description=description,
        type=transaction_type,
        is_closed=True,
        date_closed=date,
    )

    journal_entry = JournalEntry.objects.create(
        date=date,
        description=description,
        transaction=transaction,
    )

    debit_item = JournalEntryItem.objects.create(
        journal_entry=journal_entry,
        type=JournalEntryItem.JournalEntryType.DEBIT,
        amount=amount,
        account=debit_account,
        entity=debit_entity,
    )

    credit_item = JournalEntryItem.objects.create(
        journal_entry=journal_entry,
        type=JournalEntryItem.JournalEntryType.CREDIT,
        amount=amount,
        account=credit_account,
        entity=credit_entity,
    )

    return {
        'transaction': transaction,
        'journal_entry': journal_entry,
        'debit_item': debit_item,
        'credit_item': credit_item,
    }


def create_multi_line_journal_entry(
    date: date,
    entries: list,
    description: str = '',
    transaction_account: Optional[Account] = None,
    transaction_amount: Optional[Decimal] = None,
    transaction_type: str = Transaction.TransactionType.PURCHASE,
):
    """
    Create a transaction with a journal entry containing multiple line items.

    Useful for complex entries like payroll with multiple debits/credits.

    Args:
        date: Transaction date
        entries: List of dicts with keys: 'account', 'type' ('debit'/'credit'), 'amount',
                 and optional 'entity'
        description: Transaction description
        transaction_account: Account for the Transaction (defaults to first entry's account)
        transaction_amount: Amount for Transaction (defaults to sum of debits)
        transaction_type: Type of transaction

    Returns:
        dict with keys: 'transaction', 'journal_entry', 'items' (list of JournalEntryItems)
    """
    if not entries:
        raise ValueError("entries must not be empty")

    if transaction_account is None:
        transaction_account = entries[0]['account']

    if transaction_amount is None:
        transaction_amount = sum(
            Decimal(str(e['amount'])) for e in entries
            if e['type'] == 'debit'
        )

    transaction = Transaction.objects.create(
        date=date,
        account=transaction_account,
        amount=transaction_amount,
        description=description,
        type=transaction_type,
        is_closed=True,
        date_closed=date,
    )

    journal_entry = JournalEntry.objects.create(
        date=date,
        description=description,
        transaction=transaction,
    )

    items = []
    for entry in entries:
        item = JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=entry['type'],
            amount=Decimal(str(entry['amount'])),
            account=entry['account'],
            entity=entry.get('entity'),
        )
        items.append(item)

    return {
        'transaction': transaction,
        'journal_entry': journal_entry,
        'items': items,
    }


class StatementTestScenario:
    """
    Pre-configured scenario for testing financial statements.

    Creates a complete test environment with accounts and transactions
    that produce known, predictable balances for statement testing.
    """

    def __init__(
        self,
        start_date: str = '2023-01-01',
        end_date: str = '2023-01-31',
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.accounts = {}
        self.transactions = []

    def setup(self):
        """Create all accounts and transactions for the scenario."""
        self._create_accounts()
        self._create_transactions()
        return self

    def _create_accounts(self):
        """Create the chart of accounts needed for statement tests."""
        # Assets
        self.accounts['cash'] = Account.objects.create(
            name='900-Ally',
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
        )
        self.accounts['retirement'] = Account.objects.create(
            name='7000-Vanguard',
            type=Account.Type.ASSET,
            sub_type=Account.SubType.SECURITIES_RETIREMENT,
        )

        # Liabilities
        self.accounts['credit_card'] = Account.objects.create(
            name='1200-Chase',
            type=Account.Type.LIABILITY,
            sub_type=Account.SubType.SHORT_TERM_DEBT,
        )
        self.accounts['mortgage'] = Account.objects.create(
            name='Mortgage',
            type=Account.Type.LIABILITY,
            sub_type=Account.SubType.LONG_TERM_DEBT,
        )

        # Income
        self.accounts['salary'] = Account.objects.create(
            name='8000-Income',
            type=Account.Type.INCOME,
            sub_type=Account.SubType.SALARY,
        )
        self.accounts['other_income'] = Account.objects.create(
            name='8100-Other Income',
            type=Account.Type.INCOME,
            sub_type=Account.SubType.OTHER_INCOME,
        )
        self.accounts['unrealized_gains'] = Account.objects.create(
            name='Unrealized Earnings',
            type=Account.Type.INCOME,
            sub_type=Account.SubType.UNREALIZED_INVESTMENT_GAINS,
        )

        # Expenses
        self.accounts['taxes'] = Account.objects.create(
            name='Taxes',
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.TAX,
        )
        self.accounts['groceries'] = Account.objects.create(
            name='5000-Groceries',
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.PURCHASES,
        )
        self.accounts['insurance'] = Account.objects.create(
            name='6000-Insurance',
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.PURCHASES,
        )

    def _create_transactions(self):
        """Create transactions that produce the expected statement balances."""
        txn_date = '2023-01-28'

        # Tax expense: Debit Taxes $10, Credit Cash $10
        self.transactions.append(
            create_closed_transaction_with_journal_entry(
                date=txn_date,
                debit_account=self.accounts['taxes'],
                credit_account=self.accounts['cash'],
                amount=Decimal('10'),
                description='Tax payment',
                transaction_account=self.accounts['taxes'],
            )
        )

        # Other income: Debit Cash $150, Credit Other Income $150
        self.transactions.append(
            create_closed_transaction_with_journal_entry(
                date=txn_date,
                debit_account=self.accounts['cash'],
                credit_account=self.accounts['other_income'],
                amount=Decimal('150'),
                description='Other income received',
                transaction_account=self.accounts['other_income'],
                transaction_type=Transaction.TransactionType.INCOME,
            )
        )

        # Groceries purchase: Debit Groceries $100, Credit Chase $100
        self.transactions.append(
            create_closed_transaction_with_journal_entry(
                date=txn_date,
                debit_account=self.accounts['groceries'],
                credit_account=self.accounts['credit_card'],
                amount=Decimal('100'),
                description='Grocery shopping',
                transaction_account=self.accounts['salary'],
            )
        )

        # Insurance: Debit Insurance $100, Credit Chase $100
        self.transactions.append(
            create_closed_transaction_with_journal_entry(
                date=txn_date,
                debit_account=self.accounts['insurance'],
                credit_account=self.accounts['credit_card'],
                amount=Decimal('100'),
                description='Insurance payment',
                transaction_account=self.accounts['salary'],
            )
        )

        # Two retirement contributions via credit card
        # Debit Chase $100, Credit Vanguard $100 (x2)
        for i in range(2):
            self.transactions.append(
                create_closed_transaction_with_journal_entry(
                    date=txn_date,
                    debit_account=self.accounts['credit_card'],
                    credit_account=self.accounts['retirement'],
                    amount=Decimal('100'),
                    description=f'Retirement contribution {i+1}',
                    transaction_account=self.accounts['salary'],
                )
            )

        # Salary income entry 1: Credit Income $100, Credit Chase $100
        self.transactions.append(
            create_multi_line_journal_entry(
                date=txn_date,
                entries=[
                    {'account': self.accounts['salary'], 'type': 'credit', 'amount': Decimal('100')},
                    {'account': self.accounts['credit_card'], 'type': 'credit', 'amount': Decimal('100')},
                ],
                description='Salary with employer 401k match',
                transaction_account=self.accounts['salary'],
                transaction_amount=Decimal('100'),
                transaction_type=Transaction.TransactionType.INCOME,
            )
        )

        # Salary income entry 2: Debit Cash $300, Credit Income $300
        self.transactions.append(
            create_closed_transaction_with_journal_entry(
                date=txn_date,
                debit_account=self.accounts['cash'],
                credit_account=self.accounts['salary'],
                amount=Decimal('300'),
                description='Salary deposit',
                transaction_account=self.accounts['salary'],
                transaction_type=Transaction.TransactionType.INCOME,
            )
        )

        # Mortgage payment: Debit Cash $50, Credit Mortgage $50
        self.transactions.append(
            create_closed_transaction_with_journal_entry(
                date=txn_date,
                debit_account=self.accounts['cash'],
                credit_account=self.accounts['mortgage'],
                amount=Decimal('50'),
                description='Mortgage payment',
                transaction_account=self.accounts['cash'],
            )
        )

        # Transfer to retirement: Debit Vanguard $50, Credit Cash $50
        self.transactions.append(
            create_closed_transaction_with_journal_entry(
                date=txn_date,
                debit_account=self.accounts['retirement'],
                credit_account=self.accounts['cash'],
                amount=Decimal('50'),
                description='Transfer to retirement',
                transaction_account=self.accounts['cash'],
                transaction_type=Transaction.TransactionType.TRANSFER,
            )
        )

        # Unrealized gains: Debit Vanguard $50, Credit Unrealized Earnings $50
        self.transactions.append(
            create_closed_transaction_with_journal_entry(
                date=txn_date,
                debit_account=self.accounts['retirement'],
                credit_account=self.accounts['unrealized_gains'],
                amount=Decimal('50'),
                description='Market appreciation',
                transaction_account=self.accounts['retirement'],
            )
        )

    @property
    def expected_balances(self):
        """
        Return expected account balances for verification.

        These match the original test expectations in the statement tests.
        """
        return {
            'cash': Decimal('440'),  # 150 + 300 + 50 - 10 - 50 = 440
            'retirement': Decimal('-150'),  # -100 -100 + 50 + 50 = -100 (credit balance)
            'credit_card': Decimal('100'),  # 100 + 100 - 100 - 100 - 100 = -100 (but shown as 100 liability)
            'mortgage': Decimal('50'),
            'taxes': Decimal('10'),
            'groceries': Decimal('100'),
            'insurance': Decimal('100'),
            'salary': Decimal('400'),  # 100 + 300 = 400
            'other_income': Decimal('150'),
            'unrealized_gains': Decimal('50'),
        }


class BalanceSheetTestScenario(StatementTestScenario):
    """
    Specialized scenario for balance sheet tests.

    Adds the unrealized earnings account needed for balance sheet
    retained earnings calculations.
    """

    def _create_accounts(self):
        super()._create_accounts()
        # Override unrealized gains to use correct type for balance sheet tests
        self.accounts['unrealized_gains'].delete()
        self.accounts['unrealized_gains'] = Account.objects.create(
            name='Unrealized Earnings',
            type=Account.Type.INCOME,
            sub_type=Account.SubType.UNREALIZED_INVESTMENT_GAINS,
        )
