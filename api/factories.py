from api.models import Account, Reconciliation, TaxCharge
from api.services.tax_services import get_tax_accounts


class ReconciliationFactory:
    @staticmethod
    def create_bulk_reconciliations(date):
        existing_reconciliations = set(
            Reconciliation.objects.filter(date=date).values_list(
                "account__name", flat=True
            )
        )
        balance_sheet_account_names = set(
            Account.objects.filter(
                type__in=[Account.Type.ASSET, Account.Type.LIABILITY], is_closed=False
            ).values_list("name", flat=True)
        )

        new_reconciliations = balance_sheet_account_names - existing_reconciliations
        new_reconciliation_list = [
            Reconciliation(account=Account.objects.get(name=account_name), date=date)
            for account_name in new_reconciliations
        ]

        if new_reconciliation_list:
            Reconciliation.objects.bulk_create(new_reconciliation_list)

        reconciliations = Reconciliation.objects.filter(date=date)
        return reconciliations


class TaxChargeFactory:
    @staticmethod
    def create_bulk_tax_charges(date):
        tax_charges = TaxCharge.objects.filter(date=date)
        tax_accounts = get_tax_accounts()

        # Match on the charge's own account. Reaching through the transaction
        # meant an edited charge looked absent, so this re-created it and hit
        # the ("account", "date") unique constraint on every page load.
        existing_accounts = {charge.account_id for charge in tax_charges}
        for account in tax_accounts:
            if account.pk not in existing_accounts:
                TaxCharge.objects.create(date=date, account=account, amount=0)
