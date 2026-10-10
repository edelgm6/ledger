"""The Tax Rate column is only meaningful for income taxes.

The tax table guarded on ``tax_charge.type``, a field removed in migration
0011. Django resolves a missing attribute to '', so ``not '' == 'property'``
was always true and a property-tax charge rendered a rate anyway. The guard
now asks the charge's account whether it is an income tax.
"""

import datetime
from decimal import Decimal

from django.test import TestCase

from api.models import Account, TaxCharge
from api.services.tax_services import TaxChargeWithRate
from api.tests.testing_factories import AccountFactory
from api.views.tax_helpers import render_tax_table


class TaxRateColumnTest(TestCase):
    def _charge(self, tax_kind):
        payable = AccountFactory(
            type=Account.Type.LIABILITY,
            sub_type=Account.SubType.TAXES_PAYABLE,
        )
        account = AccountFactory(
            tax_kind=tax_kind,
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.TAX,
        )
        account.tax_payable_account = payable
        account.save()

        return TaxCharge.objects.create(
            account=account,
            date=datetime.date(2026, 3, 31),
            amount=Decimal("250.00"),
        )

    def _render(self, charge):
        return render_tax_table([
            TaxChargeWithRate(
                tax_charge=charge,
                taxable_income=Decimal("1000.00"),
                tax_rate=Decimal("0.25"),
                current_tax=None,
                transaction_string="charge",
            )
        ])

    def test_income_tax_charge_shows_a_rate(self):
        html = self._render(self._charge(Account.TaxKind.FEDERAL))
        self.assertIn("25.00%", html)

    def test_state_tax_charge_shows_a_rate(self):
        html = self._render(self._charge(Account.TaxKind.STATE))
        self.assertIn("25.00%", html)

    def test_property_tax_charge_shows_no_rate(self):
        html = self._render(self._charge(Account.TaxKind.PROPERTY))
        self.assertNotIn(
            "25.00%",
            html,
            "a property tax charge has no meaningful rate and must not show one",
        )
