from django.core.management.base import BaseCommand

from api.models import Account, Transaction


class Command(BaseCommand):
    help = "Seeds the database with initial Account and Transaction data"

    def handle(self, *args, **kwargs):
        # List of Account data to seed
        accounts_data = [
            {
                # INCOME, not EQUITY: UNREALIZED_INVESTMENT_GAINS belongs to
                # INCOME in SUBTYPE_TO_TYPE_MAP, and Account.save() derives
                # `type` from `sub_type`. The old EQUITY value also made the
                # get_or_create() below miss the existing row and attempt a
                # duplicate insert.
                "name": "Unrealized Gains and Losses",
                "type": Account.Type.INCOME,
                "sub_type": Account.SubType.UNREALIZED_INVESTMENT_GAINS,
                "system_role": Account.SystemRole.UNREALIZED_GAINS_AND_LOSSES,
            },
            # Taxes-payable liabilities carry no marker; they are reached via the
            # reverse of a tax account's tax_payable_account FK.
            {
                "name": "State Taxes Payable",
                "type": Account.Type.LIABILITY,
                "sub_type": Account.SubType.TAXES_PAYABLE,
            },
            {
                "name": "Federal Taxes Payable",
                "type": Account.Type.LIABILITY,
                "sub_type": Account.SubType.TAXES_PAYABLE,
            },
            {
                "name": "Property Taxes Payable",
                "type": Account.Type.LIABILITY,
                "sub_type": Account.SubType.TAXES_PAYABLE,
            },
            {
                "name": "Wallet",
                "type": Account.Type.ASSET,
                "sub_type": Account.SubType.CASH,
                "system_role": Account.SystemRole.WALLET,
            },
            {
                "name": "Prepaid Expenses",
                "type": Account.Type.ASSET,
                "sub_type": Account.SubType.PREPAID_EXPENSES,
                "system_role": Account.SystemRole.PREPAID_EXPENSES,
            },
            # Add one account for each subtype
            {
                "name": "Short Term Debt",
                "type": Account.Type.LIABILITY,
                "sub_type": Account.SubType.SHORT_TERM_DEBT,
            },
            {
                "name": "Accounts Receivable",
                "type": Account.Type.ASSET,
                "sub_type": Account.SubType.ACCOUNTS_RECEIVABLE,
            },
            {
                "name": "Retained Earnings",
                "type": Account.Type.EQUITY,
                "sub_type": Account.SubType.RETAINED_EARNINGS,
            },
            {
                "name": "Salary",
                "type": Account.Type.INCOME,
                "sub_type": Account.SubType.SALARY,
            },
            {
                "name": "Operating",
                "type": Account.Type.EXPENSE,
                "sub_type": Account.SubType.OPERATING,
            },
        ]

        for account_data in accounts_data:
            account, created = Account.objects.get_or_create(**account_data)
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Account {account.name} created.")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"Account {account.name} already exists.")
                )

        # Optionally, create some Transactions if needed
        if Account.objects.exists():
            wallet_account = Account.objects.system(Account.SystemRole.WALLET)
            Transaction.objects.get_or_create(
                date="2024-01-01",
                account=wallet_account,
                amount=1000.00,
                description="Initial Wallet Funding",
                type=Transaction.TransactionType.INCOME,
            )
            self.stdout.write(
                self.style.SUCCESS("Transaction created if it did not exist.")
            )
        else:
            self.stdout.write(
                self.style.WARNING("No accounts available for creating transactions.")
            )
