from django.test import TestCase
from api.models import Account, TaxCharge, Reconciliation

class TaxChargeTest(TestCase):
    def setUp(self):

        self.property_tax_payable = Account.objects.create(
            name = 'ptp',
            type = Account.Type.LIABILITY,
            sub_type = Account.SubType.TAXES_PAYABLE,
            special_type = Account.SpecialType.PROPERTY_TAXES_PAYABLE
        )

        self.property_tax = Account.objects.create(
            name = 'pt',
            type = Account.Type.EXPENSE,
            sub_type = Account.SubType.TAX,
            special_type = Account.SpecialType.PROPERTY_TAXES
        )

        fed_tax_payable = Account.objects.create(
            name = 'ftp',
            type = Account.Type.LIABILITY,
            sub_type = Account.SubType.TAXES_PAYABLE,
            special_type = Account.SpecialType.FEDERAL_TAXES_PAYABLE
        )

        fed_tax = Account.objects.create(
            name = 'ft',
            type = Account.Type.EXPENSE,
            sub_type = Account.SubType.TAX,
            special_type = Account.SpecialType.FEDERAL_TAXES
        )

        state_tax_payable = Account.objects.create(
            name = 'stp',
            type = Account.Type.LIABILITY,
            sub_type = Account.SubType.TAXES_PAYABLE,
            special_type = Account.SpecialType.STATE_TAXES_PAYABLE
        )

        state_tax = Account.objects.create(
            name = 'st',
            type = Account.Type.EXPENSE,
            sub_type = Account.SubType.TAX,
            special_type = Account.SpecialType.STATE_TAXES
        )

    def test_create_tax_charge(self):
        tax_charge = TaxCharge.objects.create(
            type = TaxCharge.Type.PROPERTY,
            date = '2023-05-31',
            amount = 1000
        )

        transaction = tax_charge.transaction
        self.assertEqual(transaction.amount,tax_charge.amount)
        self.assertEqual(self.property_tax.get_balance('2023-05-31','2023-05-31'), tax_charge.amount)
        self.assertEqual(self.property_tax_payable.get_balance('2023-05-31'), tax_charge.amount)

    def test_update_tax_charge_and_reconcile(self):
        reconciliation = Reconciliation.objects.create(
            account=self.property_tax_payable,
            date='2023-05-31',
            amount=2000
        )

        tax_charge = TaxCharge.objects.create(
            type = TaxCharge.Type.PROPERTY,
            date = '2023-05-31',
            amount = 1000
        )

        reconciliation = Reconciliation.objects.get(pk=reconciliation.pk)

        transaction = tax_charge.transaction
        self.assertEqual(transaction.amount,tax_charge.amount)
        self.assertEqual(self.property_tax.get_balance('2023-05-31','2023-05-31'), tax_charge.amount)
        self.assertEqual(self.property_tax_payable.get_balance('2023-05-31'), tax_charge.amount)
        self.assertEqual(reconciliation.amount, tax_charge.amount)


class ReconciliationTest(TestCase):
    def setUp(self):
        self.gain_loss_account = Account.objects.create(
            name = 'gain loss',
            type = Account.Type.EQUITY,
            sub_type = Account.SubType.UNREALIZED_INVESTMENT_GAINS,
            special_type = Account.SpecialType.UNREALIZED_GAINS_AND_LOSSES
        )

        self.plugged_account = Account.objects.create(
            name = 'robinhood',
            type = Account.Type.ASSET,
            sub_type = Account.SubType.SECURITIES_UNRESTRICTED
        )

        self.reconciliation = Reconciliation.objects.create(
            account=self.plugged_account,
            date='2023-05-31',
            amount=2000
        )

    def test_reconciliation_string(self):
        self.assertEqual(str(self.reconciliation), str(self.reconciliation.date) + ' ' + self.plugged_account.name)

    def test_reconciliation_creates_plug(self):
        self.reconciliation.plug_investment_change()

        gain_loss_account = Account.objects.get(pk=self.gain_loss_account.pk)
        self.assertEqual(gain_loss_account.get_balance('2023-05-31'), self.reconciliation.amount)

        plugged_account = Account.objects.get(pk=self.plugged_account.pk)
        self.assertEqual(plugged_account.get_balance('2023-05-31'), self.reconciliation.amount)

    def test_plug_to_overwrite_prior_plug(self):

        # Now we have a full transaction + journal entry setup
        self.reconciliation.plug_investment_change()

        # Modify reconciliation to a new amount
        self.reconciliation.amount = -500
        self.reconciliation.save()

        self.reconciliation.plug_investment_change()

        gain_loss_account = Account.objects.get(pk=self.gain_loss_account.pk)
        self.assertEqual(gain_loss_account.get_balance('2023-05-31'), self.reconciliation.amount)

        plugged_account = Account.objects.get(pk=self.plugged_account.pk)
        self.assertEqual(plugged_account.get_balance('2023-05-31'), self.reconciliation.amount)