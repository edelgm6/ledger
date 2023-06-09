import datetime
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from api.models import Account, Transaction, JournalEntry, JournalEntryItem, Reconciliation

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
        self.reconciliation.amount = 3000
        self.reconciliation.save()

        self.reconciliation.plug_investment_change()

        gain_loss_account = Account.objects.get(pk=self.gain_loss_account.pk)
        self.assertEqual(gain_loss_account.get_balance('2023-05-31'), self.reconciliation.amount)

        plugged_account = Account.objects.get(pk=self.plugged_account.pk)
        self.assertEqual(plugged_account.get_balance('2023-05-31'), self.reconciliation.amount)