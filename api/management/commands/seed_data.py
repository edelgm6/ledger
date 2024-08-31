from django.core.management.base import BaseCommand

from api.models import Account, Transaction


class Command(BaseCommand):
    help = 'Seeds the database with initial Account and Transaction data'

    def handle(self, *args, **kwargs):
        # List of Account data to seed
        accounts_data = [
            {'name': 'Unrealized Gains and Losses', 'type': Account.Type.EQUITY, 'sub_type': Account.SubType.UNREALIZED_INVESTMENT_GAINS, 'special_type': Account.SpecialType.UNREALIZED_GAINS_AND_LOSSES},
            {'name': 'State Taxes Payable', 'type': Account.Type.LIABILITY, 'sub_type': Account.SubType.TAXES_PAYABLE, 'special_type': Account.SpecialType.STATE_TAXES_PAYABLE},
            {'name': 'Federal Taxes Payable', 'type': Account.Type.LIABILITY, 'sub_type': Account.SubType.TAXES_PAYABLE, 'special_type': Account.SpecialType.FEDERAL_TAXES_PAYABLE},
            {'name': 'Property Taxes Payable', 'type': Account.Type.LIABILITY, 'sub_type': Account.SubType.TAXES_PAYABLE, 'special_type': Account.SpecialType.PROPERTY_TAXES_PAYABLE},
            {'name': 'Wallet', 'type': Account.Type.ASSET, 'sub_type': Account.SubType.CASH, 'special_type': Account.SpecialType.WALLET},
            {'name': 'Prepaid Expenses', 'type': Account.Type.ASSET, 'sub_type': Account.SubType.PREPAID_EXPENSES, 'special_type': Account.SpecialType.PREPAID_EXPENSES},
            # Add one account for each subtype
            {'name': 'Short Term Debt', 'type': Account.Type.LIABILITY, 'sub_type': Account.SubType.SHORT_TERM_DEBT},
            {'name': 'Accounts Receivable', 'type': Account.Type.ASSET, 'sub_type': Account.SubType.ACCOUNTS_RECEIVABLE},
            {'name': 'Retained Earnings', 'type': Account.Type.EQUITY, 'sub_type': Account.SubType.RETAINED_EARNINGS},
            {'name': 'Salary', 'type': Account.Type.INCOME, 'sub_type': Account.SubType.SALARY},
            {'name': 'Purchases', 'type': Account.Type.EXPENSE, 'sub_type': Account.SubType.PURCHASES},
        ]

        for account_data in accounts_data:
            account, created = Account.objects.get_or_create(**account_data)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Account {account.name} created.'))
            else:
                self.stdout.write(self.style.WARNING(f'Account {account.name} already exists.'))

        # Optionally, create some Transactions if needed
        if Account.objects.exists():
            wallet_account = Account.objects.get(name='Wallet')
            Transaction.objects.get_or_create(
                date='2024-01-01',
                account=wallet_account,
                amount=1000.00,
                description='Initial Wallet Funding',
                type=Transaction.TransactionType.INCOME
            )
            self.stdout.write(self.style.SUCCESS('Transaction created if it did not exist.'))
        else:
            self.stdout.write(self.style.WARNING('No accounts available for creating transactions.'))
