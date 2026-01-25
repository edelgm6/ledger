"""
Management command to seed the database with realistic test data for manual testing.

Usage:
    python manage.py seed_test_data              # Create 12 months of data
    python manage.py seed_test_data --months=6   # Create 6 months of data
    python manage.py seed_test_data --clear      # Clear existing data first
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction as db_transaction

from api.models import (
    Account,
    AutoTag,
    CSVColumnValuePair,
    CSVProfile,
    Entity,
    JournalEntry,
    JournalEntryItem,
    Paystub,
    PaystubValue,
    Prefill,
    PrefillItem,
    S3File,
    Transaction,
)


class Command(BaseCommand):
    help = "Seeds the database with realistic test data for manual testing"

    def add_arguments(self, parser):
        parser.add_argument(
            '--months',
            type=int,
            default=12,
            help='Number of months of transaction history to create (default: 12)',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before seeding',
        )

    def handle(self, *args, **options):
        months = options['months']
        clear = options['clear']

        if clear:
            self._clear_data()

        with db_transaction.atomic():
            self._create_test_user()
            entities = self._create_entities()
            accounts = self._create_accounts(entities)
            csv_profiles = self._create_csv_profiles()
            self._link_csv_profiles_to_accounts(accounts, csv_profiles)
            prefills = self._create_prefills(accounts, entities)
            self._create_autotags(accounts, prefills, entities)
            self._create_paystubs(accounts, entities, prefills)
            self._create_transaction_history(accounts, entities, prefills, months)
            self._create_untagged_receivables(accounts)

        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded database with {months} months of test data"
        ))

    def _clear_data(self):
        """Clear existing test data."""
        from api.models import (
            Amortization,
            Reconciliation,
            TaxCharge,
            Paystub,
            PaystubValue,
            S3File,
            DocSearch,
        )

        self.stdout.write("Clearing existing data...")

        # Delete in order of dependencies (most dependent first)
        # Due to complex FK relationships, we need to break circular dependencies
        # by nullifying some FKs before deletion

        # First, break the Transaction -> Amortization link
        Transaction.objects.filter(amortization__isnull=False).update(amortization=None)

        # Now we can safely delete in dependency order
        TaxCharge.objects.all().delete()
        Reconciliation.objects.all().delete()
        PaystubValue.objects.all().delete()
        Paystub.objects.all().delete()
        DocSearch.objects.all().delete()
        S3File.objects.all().delete()
        Amortization.objects.all().delete()
        JournalEntryItem.objects.all().delete()
        JournalEntry.objects.all().delete()
        Transaction.objects.all().delete()
        AutoTag.objects.all().delete()
        PrefillItem.objects.all().delete()
        Prefill.objects.all().delete()
        Account.objects.all().delete()
        Entity.objects.all().delete()
        CSVColumnValuePair.objects.all().delete()
        CSVProfile.objects.all().delete()

        # Delete test user if exists
        User.objects.filter(username='testuser').delete()

        self.stdout.write(self.style.SUCCESS("Data cleared"))

    def _create_test_user(self):
        """Create or get test user."""
        user, created = User.objects.get_or_create(
            username='testuser',
            defaults={
                'email': 'testuser@example.com',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created:
            user.set_password('testpass123')
            user.save()
            self.stdout.write(self.style.SUCCESS("Created test user (testuser/testpass123)"))
        else:
            self.stdout.write("Test user already exists")
        return user

    def _create_entities(self):
        """Create business entities."""
        entities = {}
        entity_data = [
            ('Self', False),
            ('Partner', False),
            ('Joint', False),
            ('Employer Inc', False),
            ('Old Job LLC', True),  # closed entity
            # Entities for accounts receivable tracking
            ('John Smith', False),
            ('Jane Doe', False),
            ('Mike Johnson', False),
            ('Freelance Client A', False),
            ('Freelance Client B', False),
        ]

        for name, is_closed in entity_data:
            entity, created = Entity.objects.get_or_create(
                name=name,
                defaults={'is_closed': is_closed}
            )
            entities[name.lower().replace(' ', '_')] = entity
            if created:
                self.stdout.write(f"  Created entity: {name}")

        return entities

    def _create_accounts(self, entities):
        """Create chart of accounts."""
        accounts = {}

        # Special accounts required by the system
        special_accounts = [
            ('Unrealized Gains and Losses', Account.Type.INCOME, Account.SubType.UNREALIZED_INVESTMENT_GAINS, Account.SpecialType.UNREALIZED_GAINS_AND_LOSSES),
            ('State Taxes Payable', Account.Type.LIABILITY, Account.SubType.TAXES_PAYABLE, Account.SpecialType.STATE_TAXES_PAYABLE),
            ('Federal Taxes Payable', Account.Type.LIABILITY, Account.SubType.TAXES_PAYABLE, Account.SpecialType.FEDERAL_TAXES_PAYABLE),
            ('Property Taxes Payable', Account.Type.LIABILITY, Account.SubType.TAXES_PAYABLE, Account.SpecialType.PROPERTY_TAXES_PAYABLE),
            ('State Taxes', Account.Type.EXPENSE, Account.SubType.TAX, Account.SpecialType.STATE_TAXES),
            ('Federal Taxes', Account.Type.EXPENSE, Account.SubType.TAX, Account.SpecialType.FEDERAL_TAXES),
            ('Property Taxes', Account.Type.EXPENSE, Account.SubType.TAX, Account.SpecialType.PROPERTY_TAXES),
            ('Wallet', Account.Type.ASSET, Account.SubType.CASH, Account.SpecialType.WALLET),
            ('Prepaid Expenses', Account.Type.ASSET, Account.SubType.PREPAID_EXPENSES, Account.SpecialType.PREPAID_EXPENSES),
            ('Starting Equity', Account.Type.EQUITY, Account.SubType.RETAINED_EARNINGS, Account.SpecialType.STARTING_EQUITY),
        ]

        for name, acct_type, sub_type, special_type in special_accounts:
            account, _ = Account.objects.get_or_create(
                name=name,
                defaults={
                    'type': acct_type,
                    'sub_type': sub_type,
                    'special_type': special_type,
                }
            )
            accounts[name.lower().replace(' ', '_').replace('-', '_')] = account

        # Link tax accounts to payable accounts
        state_taxes = Account.objects.get(special_type=Account.SpecialType.STATE_TAXES)
        state_taxes.tax_payable_account = Account.objects.get(special_type=Account.SpecialType.STATE_TAXES_PAYABLE)
        state_taxes.save()

        federal_taxes = Account.objects.get(special_type=Account.SpecialType.FEDERAL_TAXES)
        federal_taxes.tax_payable_account = Account.objects.get(special_type=Account.SpecialType.FEDERAL_TAXES_PAYABLE)
        federal_taxes.save()

        property_taxes = Account.objects.get(special_type=Account.SpecialType.PROPERTY_TAXES)
        property_taxes.tax_payable_account = Account.objects.get(special_type=Account.SpecialType.PROPERTY_TAXES_PAYABLE)
        property_taxes.save()

        # Regular accounts - Assets
        regular_accounts = [
            # Cash accounts
            ('Ally Checking', Account.Type.ASSET, Account.SubType.CASH, entities.get('self')),
            ('Ally Savings', Account.Type.ASSET, Account.SubType.CASH, entities.get('self')),
            ('Chase Checking', Account.Type.ASSET, Account.SubType.CASH, entities.get('joint')),
            ('Partner Checking', Account.Type.ASSET, Account.SubType.CASH, entities.get('partner')),

            # Securities
            ('Vanguard Brokerage', Account.Type.ASSET, Account.SubType.SECURITIES_UNRESTRICTED, entities.get('self')),
            ('Fidelity 401k', Account.Type.ASSET, Account.SubType.SECURITIES_RETIREMENT, entities.get('self')),
            ('Partner Roth IRA', Account.Type.ASSET, Account.SubType.SECURITIES_RETIREMENT, entities.get('partner')),

            # Other assets
            ('Home', Account.Type.ASSET, Account.SubType.REAL_ESTATE, entities.get('joint')),
            ('Accounts Receivable', Account.Type.ASSET, Account.SubType.ACCOUNTS_RECEIVABLE, entities.get('self')),

            # Liabilities
            ('Chase Sapphire', Account.Type.LIABILITY, Account.SubType.SHORT_TERM_DEBT, entities.get('self')),
            ('Citi Card', Account.Type.LIABILITY, Account.SubType.SHORT_TERM_DEBT, entities.get('partner')),
            ('Mortgage', Account.Type.LIABILITY, Account.SubType.LONG_TERM_DEBT, entities.get('joint')),

            # Income
            ('Salary - Self', Account.Type.INCOME, Account.SubType.SALARY, entities.get('employer_inc')),
            ('Salary - Partner', Account.Type.INCOME, Account.SubType.SALARY, entities.get('partner')),
            ('Dividends', Account.Type.INCOME, Account.SubType.DIVIDENDS_AND_INTEREST, entities.get('self')),
            ('Interest Income', Account.Type.INCOME, Account.SubType.DIVIDENDS_AND_INTEREST, entities.get('self')),
            ('Realized Gains', Account.Type.INCOME, Account.SubType.REALIZED_INVESTMENT_GAINS, entities.get('self')),
            ('Other Income', Account.Type.INCOME, Account.SubType.OTHER_INCOME, entities.get('self')),

            # Expenses
            ('Groceries', Account.Type.EXPENSE, Account.SubType.PURCHASES, None),
            ('Dining', Account.Type.EXPENSE, Account.SubType.PURCHASES, None),
            ('Utilities', Account.Type.EXPENSE, Account.SubType.PURCHASES, None),
            ('Insurance', Account.Type.EXPENSE, Account.SubType.PURCHASES, None),
            ('Entertainment', Account.Type.EXPENSE, Account.SubType.PURCHASES, None),
            ('Transportation', Account.Type.EXPENSE, Account.SubType.PURCHASES, None),
            ('Healthcare', Account.Type.EXPENSE, Account.SubType.PURCHASES, None),
            ('Mortgage Interest', Account.Type.EXPENSE, Account.SubType.INTEREST, None),

            # Equity
            ('Retained Earnings', Account.Type.EQUITY, Account.SubType.RETAINED_EARNINGS, None),
        ]

        for name, acct_type, sub_type, entity in regular_accounts:
            account, created = Account.objects.get_or_create(
                name=name,
                defaults={
                    'type': acct_type,
                    'sub_type': sub_type,
                    'entity': entity,
                }
            )
            accounts[name.lower().replace(' ', '_').replace('-', '_')] = account

        self.stdout.write(self.style.SUCCESS(f"  Created {len(accounts)} accounts"))
        return accounts

    def _create_csv_profiles(self):
        """Create CSV import profiles."""
        profiles = {}

        # Chase profile
        chase, _ = CSVProfile.objects.get_or_create(
            name='Chase',
            defaults={
                'date': 'Transaction Date',
                'description': 'Description',
                'category': 'Category',
                'inflow': 'Amount',
                'outflow': 'Amount',
                'date_format': '%m/%d/%Y',
            }
        )
        profiles['chase'] = chase

        # Ally profile
        ally, _ = CSVProfile.objects.get_or_create(
            name='Ally',
            defaults={
                'date': 'Date',
                'description': 'Description',
                'category': 'Type',
                'inflow': 'Amount',
                'outflow': 'Amount',
                'date_format': '%Y-%m-%d',
            }
        )
        profiles['ally'] = ally

        self.stdout.write(self.style.SUCCESS("  Created CSV profiles"))
        return profiles

    def _link_csv_profiles_to_accounts(self, accounts, csv_profiles):
        """Link CSV profiles to appropriate accounts."""
        # Link Chase profile
        for name in ['chase_checking', 'chase_sapphire']:
            if name in accounts:
                accounts[name].csv_profile = csv_profiles['chase']
                accounts[name].save()

        # Link Ally profile
        for name in ['ally_checking', 'ally_savings']:
            if name in accounts:
                accounts[name].csv_profile = csv_profiles['ally']
                accounts[name].save()

    def _create_prefills(self, accounts, entities):
        """Create prefill templates for common transactions."""
        prefills = {}

        # Paycheck prefill
        paycheck = Prefill.objects.create(name='Employer Inc Paycheck')
        prefills['paycheck'] = paycheck

        # Add prefill items for a paycheck
        PrefillItem.objects.create(
            prefill=paycheck,
            account=accounts.get('salary___self', accounts.get('salary', list(accounts.values())[0])),
            journal_entry_item_type=JournalEntryItem.JournalEntryType.CREDIT,
            order=1,
            entity=entities.get('employer_inc'),
        )
        if 'ally_checking' in accounts:
            PrefillItem.objects.create(
                prefill=paycheck,
                account=accounts['ally_checking'],
                journal_entry_item_type=JournalEntryItem.JournalEntryType.DEBIT,
                order=2,
            )
        if 'fidelity_401k' in accounts:
            PrefillItem.objects.create(
                prefill=paycheck,
                account=accounts['fidelity_401k'],
                journal_entry_item_type=JournalEntryItem.JournalEntryType.DEBIT,
                order=3,
            )

        # Grocery prefill
        grocery = Prefill.objects.create(name='Grocery Shopping')
        prefills['grocery'] = grocery

        self.stdout.write(self.style.SUCCESS("  Created prefills"))
        return prefills

    def _create_autotags(self, accounts, prefills, entities):
        """Create autotags for common transaction descriptions."""
        autotags = [
            ('AMAZON', accounts.get('groceries'), Transaction.TransactionType.PURCHASE, None, None),
            ('WHOLE FOODS', accounts.get('groceries'), Transaction.TransactionType.PURCHASE, prefills.get('grocery'), None),
            ('TRADER JOE', accounts.get('groceries'), Transaction.TransactionType.PURCHASE, prefills.get('grocery'), None),
            ('CHIPOTLE', accounts.get('dining'), Transaction.TransactionType.PURCHASE, None, None),
            ('STARBUCKS', accounts.get('dining'), Transaction.TransactionType.PURCHASE, None, None),
            ('UBER', accounts.get('transportation'), Transaction.TransactionType.PURCHASE, None, None),
            ('NETFLIX', accounts.get('entertainment'), Transaction.TransactionType.PURCHASE, None, None),
            ('SPOTIFY', accounts.get('entertainment'), Transaction.TransactionType.PURCHASE, None, None),
            ('ELECTRIC', accounts.get('utilities'), Transaction.TransactionType.PURCHASE, None, None),
            ('WATER', accounts.get('utilities'), Transaction.TransactionType.PURCHASE, None, None),
            ('DIRECT DEPOSIT', accounts.get('salary___self'), Transaction.TransactionType.INCOME, prefills.get('paycheck'), entities.get('employer_inc')),
        ]

        for search_string, account, txn_type, prefill, entity in autotags:
            if account:
                AutoTag.objects.get_or_create(
                    search_string=search_string,
                    defaults={
                        'account': account,
                        'transaction_type': txn_type,
                        'prefill': prefill,
                        'entity': entity,
                    }
                )

        self.stdout.write(self.style.SUCCESS("  Created autotags"))

    def _create_paystubs(self, accounts, entities, prefills):
        """Create sample paystubs for testing the paystub-to-journal-entry workflow."""
        from django.utils import timezone

        prefill = prefills.get('paycheck')
        if not prefill:
            self.stdout.write(self.style.WARNING("  Skipping paystubs - no paycheck prefill found"))
            return

        # Get required accounts
        salary_account = accounts.get('salary___self')
        federal_taxes = accounts.get('federal_taxes')
        state_taxes = accounts.get('state_taxes')
        fidelity_401k = accounts.get('fidelity_401k')
        ally_checking = accounts.get('ally_checking')

        if not all([salary_account, federal_taxes, state_taxes, fidelity_401k, ally_checking]):
            self.stdout.write(self.style.WARNING("  Skipping paystubs - missing required accounts"))
            return

        employer_entity = entities.get('employer_inc')

        # Define different amounts for each paystub
        paystub_data = [
            {
                'title': 'Employer Inc - Jan 15 2025',
                'gross': Decimal('4000.00'),
                'federal': Decimal('600.00'),
                'state': Decimal('200.00'),
                'retirement': Decimal('400.00'),
                'net': Decimal('2800.00'),
            },
            {
                'title': 'Employer Inc - Jan 31 2025',
                'gross': Decimal('4250.00'),  # Different amount (overtime)
                'federal': Decimal('650.00'),
                'state': Decimal('215.00'),
                'retirement': Decimal('425.00'),
                'net': Decimal('2960.00'),
            },
        ]

        today = date.today()

        for i, data in enumerate(paystub_data):
            # Create the S3File and Paystub
            s3file = S3File.objects.create(
                prefill=prefill,
                url=f"https://example-bucket.s3.amazonaws.com/paystub_{i+1}.pdf",
                user_filename=f"paystub_{i+1}.pdf",
                s3_filename=f"paystub_{i+1}.pdf",
                textract_job_id=f"textract_job_{i+1}",
                analysis_complete=timezone.now(),
            )

            paystub = Paystub.objects.create(
                document=s3file,
                page_id=f"page_{i+1}",
                title=data['title'],
                journal_entry=None,
            )

            # Create PaystubValues for this paycheck
            values = [
                (salary_account, data['gross'], JournalEntryItem.JournalEntryType.CREDIT, employer_entity),
                (federal_taxes, data['federal'], JournalEntryItem.JournalEntryType.DEBIT, None),
                (state_taxes, data['state'], JournalEntryItem.JournalEntryType.DEBIT, None),
                (fidelity_401k, data['retirement'], JournalEntryItem.JournalEntryType.DEBIT, None),
                (ally_checking, data['net'], JournalEntryItem.JournalEntryType.DEBIT, None),
            ]

            for account, amount, item_type, entity in values:
                PaystubValue.objects.create(
                    paystub=paystub,
                    account=account,
                    amount=amount,
                    journal_entry_item_type=item_type,
                    entity=entity,
                )

            # Create corresponding open transaction (paycheck deposit into Ally Checking)
            Transaction.objects.create(
                date=today - timedelta(days=i + 1),
                account=ally_checking,
                amount=data['net'],  # Positive amount = money deposited
                description=f"DIRECT DEPOSIT EMPLOYER INC - {data['title']}",
                type=Transaction.TransactionType.INCOME,
                suggested_account=salary_account,
                suggested_entity=employer_entity,
                prefill=prefill,
                is_closed=False,
            )

        self.stdout.write(self.style.SUCCESS("  Created 2 sample paystubs with matching open transactions"))

    def _create_transaction_history(self, accounts, entities, prefills, months):
        """Create realistic transaction history."""
        self.stdout.write(f"Creating {months} months of transactions...")

        end_date = date.today()
        start_date = end_date - timedelta(days=months * 30)

        transaction_patterns = self._get_transaction_patterns(accounts)
        closed_count = 0
        open_count = 0

        current_date = start_date
        while current_date <= end_date:
            # Generate daily transactions
            for pattern in transaction_patterns:
                if self._should_generate_transaction(pattern, current_date):
                    is_closed = current_date < (end_date - timedelta(days=14))

                    self._create_transaction_from_pattern(
                        pattern, current_date, accounts, entities, is_closed
                    )

                    if is_closed:
                        closed_count += 1
                    else:
                        open_count += 1

            current_date += timedelta(days=1)

        self.stdout.write(self.style.SUCCESS(
            f"  Created {closed_count} closed and {open_count} open transactions"
        ))

    def _get_transaction_patterns(self, accounts):
        """Define transaction patterns with frequency and amount ranges."""
        return [
            # Daily small purchases
            {
                'description_choices': ['STARBUCKS', 'COFFEE', 'LUNCH'],
                'account': accounts.get('chase_sapphire'),
                'amount_range': (5, 25),
                'frequency': 0.7,  # 70% chance per day
                'type': Transaction.TransactionType.PURCHASE,
                'suggested_account': accounts.get('dining'),
            },
            # Weekly groceries
            {
                'description_choices': ['WHOLE FOODS', 'TRADER JOE', 'COSTCO'],
                'account': accounts.get('chase_sapphire'),
                'amount_range': (50, 200),
                'frequency': 0.14,  # ~1 per week
                'type': Transaction.TransactionType.PURCHASE,
                'suggested_account': accounts.get('groceries'),
            },
            # Monthly utilities
            {
                'description_choices': ['ELECTRIC BILL', 'WATER BILL', 'GAS BILL'],
                'account': accounts.get('ally_checking'),
                'amount_range': (80, 200),
                'frequency': 0.033,  # ~1 per month
                'type': Transaction.TransactionType.PURCHASE,
                'suggested_account': accounts.get('utilities'),
            },
            # Bi-weekly paycheck
            {
                'description_choices': ['DIRECT DEPOSIT EMPLOYER INC'],
                'account': accounts.get('ally_checking'),
                'amount_range': (3000, 4000),
                'frequency': 0.07,  # ~2 per month
                'type': Transaction.TransactionType.INCOME,
                'suggested_account': accounts.get('salary___self'),
                'is_income': True,
            },
            # Monthly entertainment
            {
                'description_choices': ['NETFLIX', 'SPOTIFY', 'HBO'],
                'account': accounts.get('chase_sapphire'),
                'amount_range': (10, 20),
                'frequency': 0.033,
                'type': Transaction.TransactionType.PURCHASE,
                'suggested_account': accounts.get('entertainment'),
            },
            # Random transfers
            {
                'description_choices': ['TRANSFER TO SAVINGS', 'SAVINGS CONTRIBUTION'],
                'account': accounts.get('ally_checking'),
                'amount_range': (100, 500),
                'frequency': 0.05,
                'type': Transaction.TransactionType.TRANSFER,
                'suggested_account': accounts.get('ally_savings'),
            },
            # Accounts Receivable - Loans to friends/family
            {
                'description_choices': ['LOAN TO JOHN', 'LOAN TO JANE', 'LOAN TO MIKE'],
                'account': accounts.get('ally_checking'),
                'amount_range': (50, 500),
                'frequency': 0.02,  # ~1 per month
                'type': Transaction.TransactionType.PURCHASE,
                'suggested_account': accounts.get('accounts_receivable'),
                'is_receivable': True,
                'receivable_entities': ['john_smith', 'jane_doe', 'mike_johnson'],
            },
            # Accounts Receivable - Loan repayments
            {
                'description_choices': ['REPAYMENT FROM JOHN', 'REPAYMENT FROM JANE', 'REPAYMENT FROM MIKE'],
                'account': accounts.get('ally_checking'),
                'amount_range': (25, 200),
                'frequency': 0.015,  # slightly less than loans
                'type': Transaction.TransactionType.INCOME,
                'suggested_account': accounts.get('accounts_receivable'),
                'is_receivable': True,
                'receivable_entities': ['john_smith', 'jane_doe', 'mike_johnson'],
            },
            # Freelance income (invoiced but tracked via AR)
            {
                'description_choices': ['FREELANCE PROJECT', 'CONSULTING FEE', 'CONTRACT WORK'],
                'account': accounts.get('ally_checking'),
                'amount_range': (500, 2000),
                'frequency': 0.02,
                'type': Transaction.TransactionType.INCOME,
                'suggested_account': accounts.get('accounts_receivable'),
                'is_receivable': True,
                'receivable_entities': ['freelance_client_a', 'freelance_client_b'],
            },
        ]

    def _should_generate_transaction(self, pattern, current_date):
        """Determine if a transaction should be generated based on pattern frequency."""
        return random.random() < pattern['frequency']

    def _create_transaction_from_pattern(self, pattern, txn_date, accounts, entities, is_closed):
        """Create a transaction from a pattern."""
        if not pattern.get('account'):
            return None

        description = random.choice(pattern['description_choices'])
        min_amt, max_amt = pattern['amount_range']
        amount = Decimal(str(round(random.uniform(min_amt, max_amt), 2)))

        # For purchases on credit cards, amount is negative (money out)
        if pattern['type'] == Transaction.TransactionType.PURCHASE:
            amount = -amount

        transaction = Transaction.objects.create(
            date=txn_date,
            account=pattern['account'],
            amount=amount,
            description=description,
            type=pattern['type'],
            suggested_account=pattern.get('suggested_account'),
            is_closed=is_closed,
            date_closed=txn_date if is_closed else None,
        )

        # Create journal entry for closed transactions
        if is_closed and pattern.get('suggested_account'):
            journal_entry = JournalEntry.objects.create(
                date=txn_date,
                description=description,
                transaction=transaction,
            )

            # Determine debit and credit accounts based on transaction type
            if pattern['type'] == Transaction.TransactionType.INCOME:
                debit_account = pattern['account']
                credit_account = pattern['suggested_account']
            else:
                debit_account = pattern['suggested_account']
                credit_account = pattern['account']

            # Select entity for receivable transactions
            receivable_entity = None
            if pattern.get('is_receivable') and pattern.get('receivable_entities'):
                entity_key = random.choice(pattern['receivable_entities'])
                receivable_entity = entities.get(entity_key)

            # Assign entity to the accounts receivable item
            debit_entity = receivable_entity if debit_account == pattern.get('suggested_account') and pattern.get('is_receivable') else None
            credit_entity = receivable_entity if credit_account == pattern.get('suggested_account') and pattern.get('is_receivable') else None

            JournalEntryItem.objects.create(
                journal_entry=journal_entry,
                type=JournalEntryItem.JournalEntryType.DEBIT,
                amount=abs(amount),
                account=debit_account,
                entity=debit_entity,
            )

            JournalEntryItem.objects.create(
                journal_entry=journal_entry,
                type=JournalEntryItem.JournalEntryType.CREDIT,
                amount=abs(amount),
                account=credit_account,
                entity=credit_entity,
            )

        return transaction

    def _create_untagged_receivables(self, accounts):
        """Create some untagged receivable items for testing the tagging UI."""
        ar_account = accounts.get('accounts_receivable')
        checking_account = accounts.get('ally_checking')

        if not ar_account or not checking_account:
            return

        untagged_transactions = [
            ('VENMO PAYMENT RECEIVED', Decimal('75.00')),
            ('ZELLE FROM UNKNOWN', Decimal('150.00')),
            ('CHECK DEPOSIT', Decimal('200.00')),
            ('CASH APP PAYMENT', Decimal('50.00')),
            ('PAYPAL TRANSFER', Decimal('125.00')),
        ]

        today = date.today()
        for i, (description, amount) in enumerate(untagged_transactions):
            txn_date = today - timedelta(days=i + 1)

            transaction = Transaction.objects.create(
                date=txn_date,
                account=checking_account,
                amount=amount,
                description=description,
                type=Transaction.TransactionType.INCOME,
                suggested_account=ar_account,
                is_closed=True,
                date_closed=txn_date,
            )

            journal_entry = JournalEntry.objects.create(
                date=txn_date,
                description=description,
                transaction=transaction,
            )

            # Debit checking (cash in)
            JournalEntryItem.objects.create(
                journal_entry=journal_entry,
                type=JournalEntryItem.JournalEntryType.DEBIT,
                amount=amount,
                account=checking_account,
                entity=None,
            )

            # Credit AR (reducing receivable) - NO ENTITY, needs tagging
            JournalEntryItem.objects.create(
                journal_entry=journal_entry,
                type=JournalEntryItem.JournalEntryType.CREDIT,
                amount=amount,
                account=ar_account,
                entity=None,  # Intentionally untagged
            )

        self.stdout.write(self.style.SUCCESS(
            f"  Created {len(untagged_transactions)} untagged receivable items for testing"
        ))
