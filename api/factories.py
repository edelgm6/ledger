from api.models import Reconciliation, Account, TaxCharge


class ReconciliationFactory:

    @staticmethod
    def create_bulk_reconciliations(date):
        existing_reconciliations = set(
            Reconciliation.objects.filter(
                date=date
            ).values_list('account__name', flat=True)
        )
        balance_sheet_account_names = set(Account.objects.filter(
            type__in=[Account.Type.ASSET, Account.Type.LIABILITY],
            is_closed=False
        ).values_list('name', flat=True))

        new_reconciliations = (
            balance_sheet_account_names - existing_reconciliations
        )
        new_reconciliation_list = [
            Reconciliation(
                account=Account.objects.get(
                    name=account_name
                ),
                date=date
            )
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
        for value, _ in TaxCharge.Type.choices:
            existing_tax_charge = [
                charge for charge in tax_charges if charge.type == value
            ]
            if len(existing_tax_charge) == 0:
                TaxCharge.objects.create(date=date, type=value, amount=0)
