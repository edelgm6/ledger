from api.models import Reconciliation, Account

class ReconciliationFactory:

    @staticmethod
    def create_bulk_reconciliations(date):
        existing_reconciliations = set(Reconciliation.objects.filter(date=date).values_list('account__name', flat=True))
        balance_sheet_account_names = set(Account.objects.filter(type__in=[Account.Type.ASSET, Account.Type.LIABILITY]).values_list('name', flat=True))

        new_reconciliations = balance_sheet_account_names - existing_reconciliations
        new_reconciliation_list = [
            Reconciliation(account=Account.objects.get(name=account_name), date=date)
            for account_name in new_reconciliations
        ]

        if new_reconciliation_list:
            Reconciliation.objects.bulk_create(new_reconciliation_list)

        reconciliations = Reconciliation.objects.filter(date=date)
        return reconciliations
